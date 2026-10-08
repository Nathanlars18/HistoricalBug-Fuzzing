"""No-LLM regressions against real pilot inputs and adversarial candidates."""
from __future__ import annotations

import argparse
import copy
import json
import subprocess
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import build_strategy_plan_json as builder
import build_harness_artifact as emitter
from strategy_domains import infer_domains, exploration_domain_error

ROOT = Path('experiment/EXP011_bug_aware_harness_synthesis')


def load(path):
    return json.loads(Path(path).read_text())


def pilot(api):
    batch = api == 'torch.batch_norm_update_stats'
    hsrev, apirev = (4, 7) if batch else (3, 6)
    directory = api.replace('.', '_')
    spec_path = ROOT / f'harness_specs/pytorch/{api}/controlled_baseline/hs_pytorch_{api}_controlled_baseline_r{hsrev}.json'
    review_path = ROOT / f'harness_spec_reviews/pytorch/{api}/controlled_baseline/hs_pytorch_{api}_controlled_baseline_r{hsrev}__review_r1.json'
    plan_path = ROOT / f'strategy_primitives/plans/pytorch/{directory}/controlled_baseline/st_hs_pytorch_{directory}_controlled_baseline_hsr{hsrev:03d}_r001.json'
    operator = 'batch_norm_update_stats' if batch else 'cosine_embedding_loss'
    profile = load(ROOT / f'api_profiles/pytorch/v2.10.0/cpu/{api}/api_profile__aten.{operator}.default__r{apirev:03d}.json')
    catalog = load(ROOT / 'strategy_primitives/strategy_primitive_catalog.json')
    spec = load(spec_path)
    resolved = builder.ResolvedInputs(spec=spec, api=profile,
        resolved_api_primitive=builder.resolve_api_primitive(catalog, profile),
        candidate_primitives=catalog['primitives'], harness_spec_review_ref=load(plan_path)['source_context']['harness_spec_review_ref'])
    return spec_path, review_path, plan_path, catalog, resolved


def fix_batch(plan):
    plan = copy.deepcopy(plan)
    steps = plan['branch_strategies'][0]['steps']
    steps[0]['parameter_bindings'].append({'parameter_id': 'minimum_dimension', 'binding_kind': 'literal', 'binding_value': 1})
    reference = steps[0]['output_bindings'][0]['value_id']
    for step in steps[1:3]:
        step['primitive_id'] = 'construct_tensor_from_reference'
        step['input_bindings'].append({'port_id': 'reference', 'value_ref': reference})
        step['parameter_bindings'] = [
            {'parameter_id': key, 'binding_kind': 'literal', 'binding_value': value}
            for key, value in {'shape_policy': 'selected_dimension', 'reference_axis': 1,
                               'dtype_policy': 'float32', 'fill_policy': 'fuzz_numeric'}.items()]
    return plan

def static_fixture(api):
    """Deterministic test fixture, not a generated/approved experimental Plan."""
    *_, catalog, base = pilot(api)
    batch = api == 'torch.batch_norm_update_stats'
    hsrev = 6 if batch else 4
    spec = load(ROOT / f'harness_specs/pytorch/{api}/bug_aware_static/hs_pytorch_{api}_bug_aware_static_r{hsrev}.json')
    resolved = builder.ResolvedInputs(spec=spec, api=base.api, resolved_api_primitive=base.resolved_api_primitive,
        candidate_primitives=base.candidate_primitives, harness_spec_review_ref=base.harness_spec_review_ref)
    _, _, old, _, _ = pilot(api)
    default = fix_batch(load(old)['implementation_plan']) if batch else copy.deepcopy(load(old)['implementation_plan'])
    branch = copy.deepcopy(default['branch_strategies'][0])
    source = next(b for b in spec['exploration_plan']['branches'] if b['branch_kind'] == 'knowledge_directed')
    branch['source_branch_id'] = source['branch_id']
    steps = branch['steps']
    if batch:
        steps[0]['parameter_bindings'] = [b for b in steps[0]['parameter_bindings'] if b['parameter_id'] != 'minimum_dimension']
    else:
        # Independent rank/dimension choices preserve equality, mismatch, empty,
        # and nonempty cases. Target rank follows input1 without fixing a trigger.
        for step in steps[:2]:
            step['primitive_id'] = 'construct_tensor_with_rank_range'
            step['input_bindings'] = [b for b in step['input_bindings'] if b['port_id'] != 'reference']
            step['parameter_bindings'] = [
                {'parameter_id': k, 'binding_kind': 'literal', 'binding_value': v}
                for k, v in {'minimum_rank': 1, 'maximum_rank': 2,
                             'dtype_policy': 'float32', 'fill_policy': 'fuzz_numeric',
                             'max_dimension': 2, 'minimum_dimension': 0}.items()]
        steps[2]['parameter_bindings'] = [
            {'parameter_id': k, 'binding_kind': 'literal', 'binding_value': v}
            for k, v in {'shape_policy': 'drop_last_dimension',
                         'dtype_policy': 'int64', 'fill_policy': 'fuzz_sign'}.items()]
    target = steps.pop()
    branch['spec_bindings'] = []
    for index, condition in enumerate(source['target_conditions']):
        predicate = condition['predicate']
        a = predicate['arguments']
        cross = predicate['predicate_id'] == 'cross_subject_relation'
        inputs = ({'left': builder.python_subject_target_value(a['left_subject_ref'], target, base.api),
                   'right': builder.python_subject_target_value(a['right_subject_ref'], target, base.api)} if cross else
                  {'subject': builder.python_subject_target_value(a['subject_ref'], target, base.api)})
        params = ({'property_kind': a['left_property_ref'], 'relation_kind': a['relation']} if cross else
                  {'property_kind': 'numel_equals_zero', 'axis': 0, 'expected_integer': 0})
        step = {'step_id': f'step_observe_{index}', 'primitive_id': 'evaluate_tensor_relation' if cross else 'evaluate_tensor_property',
                'template_slot': 'pre_call_observation', 'input_bindings': [{'port_id': k, 'value_ref': v} for k, v in inputs.items()],
                'parameter_bindings': [{'parameter_id': k, 'binding_kind': 'literal', 'binding_value': v} for k, v in params.items()],
                'output_bindings': [{'port_id': 'relation_holds' if cross else 'property_holds', 'value_id': f'condition_result_{index}'}]}
        steps.append(step)
        branch['spec_bindings'].append({'spec_element_type': 'target_condition', 'spec_element_id': condition['condition_id'],
            'binding_kind': 'in_harness_steps', 'implementation_step_ids': [step['step_id']], 'runner_events': []})
    steps.append(target)
    for observation in source['behavior_observations']:
        branch['spec_bindings'].append({'spec_element_type': 'behavior_observation', 'spec_element_id': observation['observation_id'],
            'binding_kind': 'runner_event', 'implementation_step_ids': [], 'runner_events': sorted(builder.RUNNER_EVENTS)})
    plan = {'branch_strategies': [*default['branch_strategies'], branch]}
    builder.materialize_failure_handlers(plan, resolved)
    return plan, resolved, catalog


class PreflightTests(unittest.TestCase):
    def test_cosine_static_mask_is_rejected_and_general_rank_fixture_passes(self):
        plan, resolved, catalog = static_fixture('torch.nn.functional.cosine_embedding_loss')
        actual = load(ROOT / 'strategy_primitives/plans/pytorch/torch_nn_functional_cosine_embedding_loss/bug_aware_static/st_hs_pytorch_torch_nn_functional_cosine_embedding_loss_bug_aware_static_hsr004_r001.json')
        with self.assertRaisesRegex(builder.PlanValidationError, 'Auxiliary argument relation'):
            builder.validate_materialized_plan(actual['implementation_plan'], resolved, catalog)
        builder.materialize_failure_handlers(plan, resolved)
        builder.validate_materialized_plan(plan, resolved, catalog)

    def test_rank_range_and_drop_last_preserve_correlated_rank_domain(self):
        def step(step_id, pid, cursor, output, params, reference=None):
            inputs = [{'port_id': k, 'value_ref': v} for k, v in
                      {'data': 'data', 'size': 'size', 'cursor': cursor}.items()]
            if reference:
                inputs.insert(0, {'port_id': 'reference', 'value_ref': reference})
            return {'step_id': step_id, 'primitive_id': pid, 'input_bindings': inputs,
                    'parameter_bindings': [{'parameter_id': k, 'binding_kind': 'literal', 'binding_value': v} for k, v in params.items()],
                    'output_bindings': [{'port_id': 'tensor', 'value_id': output}, {'port_id': 'next_cursor', 'value_id': output + '_cursor'}]}
        rank = {'minimum_rank': 1, 'maximum_rank': 2, 'minimum_dimension': 0,
                'max_dimension': 4, 'dtype_policy': 'float32', 'fill_policy': 'fuzz_numeric'}
        steps = [step('a', 'construct_tensor_with_rank_range', 'offset', 'x', rank),
                 step('b', 'construct_tensor_from_reference', 'x_cursor', 'target',
                      {'shape_policy': 'drop_last_dimension', 'dtype_policy': 'int64', 'fill_policy': 'fuzz_sign'}, 'x')]
        domains = infer_domains(steps)
        self.assertEqual({len(s) for s in domains['x']['shape_alternatives']}, {1, 2})
        self.assertEqual({len(s) for s in domains['target']['shape_alternatives']}, {0, 1})
        rule = load(ROOT / 'strategy_primitives/strategy_primitive_catalog.json')['argument_relation_rules']
        target = {'input_bindings': [
            {'port_id': 'binding_param_000_input1', 'value_ref': 'x'},
            {'port_id': 'binding_param_002_target', 'value_ref': 'target'}]}
        from strategy_domains import companion_relation_errors
        self.assertEqual(companion_relation_errors({'target_conditions': [], 'branch_constraints': []}, domains, target, rule), [])

    def test_both_static_sources_are_materializable_without_ordinary_guards(self):
        for api in ('torch.batch_norm_update_stats', 'torch.nn.functional.cosine_embedding_loss'):
            plan, resolved, catalog = static_fixture(api)
            builder.capability_preflight(resolved, catalog)
            builder.validate_materialized_plan(plan, resolved, catalog)
            self.assertEqual(builder.materialization_preflight({'implementation_plan': plan}, resolved, catalog, {})['status'], 'passed')

    def test_real_cosine_validates_without_changing_implementation(self):
        _, _, path, catalog, resolved = pilot('torch.nn.functional.cosine_embedding_loss')
        plan = load(path)['implementation_plan']
        builder.validate_materialized_plan(plan, resolved, catalog)
        record = load(path)
        record['source_context']['strategy_catalog_ref']['catalog_version'] = 6
        self.assertEqual(builder.materialization_preflight(record, resolved, catalog, {})['status'], 'passed')

    def test_batch_old_recipe_rejected_new_dynamic_recipe_passes(self):
        _, _, path, catalog, resolved = pilot('torch.batch_norm_update_stats')
        record = load(path)
        with self.assertRaisesRegex(builder.PlanValidationError, 'Ordinary-input recipe'):
            builder.validate_materialized_plan(record['implementation_plan'], resolved, catalog)
        plan = fix_batch(record['implementation_plan'])
        builder.materialize_failure_handlers(plan, resolved)
        builder.validate_materialized_plan(plan, resolved, catalog)
        record['implementation_plan'] = plan
        self.assertEqual(builder.materialization_preflight(record, resolved, catalog, {})['status'], 'passed')

    def test_batch_optional_none_is_legal(self):
        _, _, path, catalog, resolved = pilot('torch.batch_norm_update_stats')
        plan = fix_batch(load(path)['implementation_plan'])
        steps = plan['branch_strategies'][0]['steps']
        # Delete auxiliary stat constructors rather than leave unused steps.
        del steps[1:3]
        steps[1]['input_bindings'] = [dict(b, value_ref=steps[0]['output_bindings'][1]['value_id']) if b['port_id'] == 'cursor' else b for b in steps[1]['input_bindings']]
        for b in steps[-1]['input_bindings']:
            if b['port_id'] in {'binding_param_001_running_mean', 'binding_param_002_running_var'}:
                b['value_ref'] = 'none'
        builder.materialize_failure_handlers(plan, resolved)
        builder.validate_materialized_plan(plan, resolved, catalog)

    def test_omitted_middle_default_rejected_before_emission(self):
        _, _, path, catalog, resolved = pilot('torch.nn.functional.cosine_embedding_loss')
        plan = copy.deepcopy(load(path)['implementation_plan'])
        plan['branch_strategies'][0]['steps'][-1]['input_bindings'].append({'port_id': 'binding_param_004_reduction', 'value_ref': 'size'})
        with self.assertRaisesRegex(builder.PlanValidationError, 'later argument'):
            builder.validate_materialized_plan(plan, resolved, catalog)

    def test_original_case_not_truncated_excerpt(self):
        *_, resolved = pilot('torch.nn.functional.cosine_embedding_loss')
        witnesses = builder.validated_ordinary_witnesses(resolved.api)
        self.assertEqual(witnesses[0]['arguments'][0]['value']['shape'], [2, 3])
        broken = copy.deepcopy(resolved.api)
        next(e for e in broken['evidence'] if e['source_kind'] == 'validation_case')['content_hash'] = '0' * 64
        with self.assertRaisesRegex(builder.ItemInputError, 'hash mismatch'):
            builder.validated_ordinary_witnesses(broken)

    def test_numel_variable_needs_both_outcomes(self):
        predicate = {'predicate_id': 'property_relation', 'arguments': {'subject_ref': 'x', 'property_ref': 'numel', 'operator': 'equals', 'value': 0}}
        for shape, accepted in [([0, -1], False), ([2, 2], False), ([-1, -1], True)]:
            step = {'step_id': 's', 'primitive_id': 'construct_tensor_with_constraints', 'input_bindings': [],
                    'parameter_bindings': [{'parameter_id': k, 'binding_kind': 'literal', 'binding_value': v} for k, v in {'shape_template': shape, 'max_dimension': 4, 'fill_policy': 'fuzz_numeric'}.items()],
                    'output_bindings': [{'port_id': 'tensor', 'value_id': 'x'}]}
            error = exploration_domain_error(predicate, infer_domains([step]))
            self.assertEqual(error is None, accepted)

    def test_shape_relation_reference_invariant_rejected(self):
        predicate = {'predicate_id': 'cross_subject_relation', 'arguments': {'left_subject_ref': 'x', 'right_subject_ref': 'y', 'left_property_ref': 'shape', 'right_property_ref': 'shape', 'relation': 'not_equals'}}
        d = {'kind': 'tensor', 'shape': [(0, 4, ('s', 0)), (0, 4, ('s', 1))]}
        self.assertIn('invariant', exploration_domain_error(predicate, {'x': d, 'y': d}))
        independent = {'kind': 'tensor', 'shape': [(0, 4, ('t', 0)), (0, 4, ('t', 1))]}
        self.assertIsNone(exploration_domain_error(predicate, {'x': d, 'y': independent}))

    def test_fuzz_sign_and_degenerate_scalar(self):
        def step(pid, params):
            return {'primitive_id': pid, 'parameter_bindings': [{'parameter_id': k, 'binding_kind': 'literal', 'binding_value': v} for k, v in params.items()]}
        self.assertIn('tensor', builder.directly_fuzz_dependent_output_ports(step('construct_tensor_with_constraints', {'shape_template': [2, 2], 'fill_policy': 'fuzz_sign'})))
        self.assertEqual(builder.directly_fuzz_dependent_output_ports(step('construct_integer_from_fuzz', {'minimum': 1, 'maximum': 1})), set())

    def test_two_phase_observation_has_distinct_sites(self):
        from test_build_harness_artifact import strategy, harness_spec, resolved_inputs, materialize
        plan, spec = strategy(), harness_spec()
        branch = plan['implementation_plan']['branch_strategies'][0]
        after = copy.deepcopy(branch['steps'][2])
        after['step_id'] = 'step_observe_zero_after'
        after['template_slot'] = 'post_call_observation'
        after['output_bindings'][0]['value_id'] = 'zero_observed_after'
        branch['steps'].append(after)
        branch['spec_bindings'][0]['implementation_step_ids'].append(after['step_id'])
        spec['exploration_plan']['branches'][0]['target_conditions'][0]['observe_at'].append('after_target_api_call')
        _, _, events = materialize(resolved_inputs(strategy_record=plan, harness_spec_record=spec))
        keys = [e['event_key'] for e in events]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(sum(e['event_kind'] == 'observation_captured' for e in events), 2)

    def test_integer_range_and_nonfinite_bounds(self):
        from test_build_harness_artifact import emitter_context, MODULE
        context = emitter_context('construct_integer_from_fuzz', parameters={'minimum': -1000, 'maximum': 1000},
            inputs={'data': 'data', 'size': 'size', 'cursor': 'offset'}, outputs={'value': 'integer', 'next_cursor': 'cursor_next'})
        atoms = MODULE.emit_construct_scalar_from_fuzz(context).atoms
        self.assertTrue(any(isinstance(a, str) and 'i < 2U' in a for a in atoms))
        for params in ({'minimum': 0, 'maximum': 2**63}, {'minimum': 0, 'maximum': float('inf')}):
            context = emitter_context('construct_integer_from_fuzz', parameters=params,
                inputs={'data': 'data', 'size': 'size', 'cursor': 'offset'}, outputs={'value': 'integer', 'next_cursor': 'cursor_next'})
            with self.assertRaises(MODULE.MaterializationError):
                MODULE.emit_construct_scalar_from_fuzz(context)

    def test_scalar_cpp_boundaries_and_boolean_execute(self):
        from test_build_harness_artifact import emitter_context, MODULE
        compiler = shutil.which('g++') or shutil.which('clang++')
        if compiler is None:
            self.skipTest('C++ compiler unavailable')
        functions = []
        cases = [
            ('construct_integer_from_fuzz', {'minimum': -(2**63), 'maximum': 2**63 - 1}, 'assert(value == 9223372036854775807LL); assert(next_cursor == 8);'),
            ('construct_integer_from_fuzz', {'minimum': -1000, 'maximum': 1000}, 'assert(value >= -1000 && value <= 1000); assert(next_cursor == 2);'),
            ('construct_boolean_from_fuzz', {}, 'assert(value); assert(next_cursor == 1);'),
            ('construct_floating_from_fuzz', {'minimum': 0.0, 'maximum': 1e308}, 'assert(std::isfinite(value)); assert(value == 1e308);'),
            ('construct_floating_from_fuzz', {'minimum': -1e308, 'maximum': 1e308}, 'assert(std::isfinite(value)); assert(value == 1e308);'),
        ]
        for i, (pid, parameters, assertion) in enumerate(cases):
            context = emitter_context(pid, parameters=parameters,
                inputs={'data': 'data', 'size': 'size', 'cursor': 'offset'}, outputs={'value': 'value', 'next_cursor': 'next_cursor'})
            body = '\n'.join(a for a in MODULE.emit_construct_scalar_from_fuzz(context).atoms if isinstance(a, str))
            functions.append(f'int test_{i}() {{ const std::uint8_t data[8] = {{255,255,255,255,255,255,255,255}}; const std::size_t size=8, offset=0; {body} {assertion} return 0; }}')
        source = '#include <cstddef>\n#include <cstdint>\n#include <cassert>\n#include <cmath>\n' + '\n'.join(functions) + '\nint main() { ' + ''.join(f'test_{i}();' for i in range(len(cases))) + ' return 0; }'
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            (path / 'scalar.cpp').write_text(source)
            compile_result = subprocess.run([compiler, '-std=c++17', '-Wall', '-Werror', str(path / 'scalar.cpp'), '-o', str(path / 'scalar')], capture_output=True, text=True, timeout=30)
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
            run = subprocess.run([str(path / 'scalar')], capture_output=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_optional_tensor_selection_consumes_a_bit(self):
        from test_build_harness_artifact import emitter_context, MODULE
        context = emitter_context('select_optional_tensor_from_fuzz',
            inputs={'tensor': 'tensor', 'data': 'data', 'size': 'size', 'cursor': 'cursor'},
            outputs={'optional_value': 'maybe_tensor', 'next_cursor': 'next_cursor'})
        result = MODULE.emit_select_optional_tensor_from_fuzz(context)
        self.assertIn('std::optional<at::Tensor> maybe_tensor;', result.atoms)
        self.assertTrue(any('data[next_cursor++] & 1U' in a for a in result.atoms if isinstance(a, str)))

    def test_scalar_output_shape_and_preferred_not_abort(self):
        from test_build_harness_artifact import emitter_context, MODULE
        check = {'check_id': 'check_scalar', 'requirement_level': 'preferred'}
        context = emitter_context('evaluate_output_property',
            inputs={'result': 'result'}, parameters={'check_kind': 'shape_equals', 'expected_shape': [], 'expected_integer': 0},
            outputs={'oracle_holds': 'holds'}, spec_bindings=({'spec_element_type': 'behavior_check', 'spec_element_id': 'check_scalar'},))
        context.harness_spec['exploration_plan']['branches'][0]['behavior_checks'] = [check]
        result = MODULE.emit_evaluate_output_property(context)
        self.assertIn('const bool holds = (result.dim() == 0);', result.atoms)
        self.assertFalse(any('std::abort' in a for a in result.atoms if isinstance(a, str)))

    def test_return_conversion_is_explicit_capability_gap(self):
        *_, resolved = pilot('torch.batch_norm_update_stats')
        profile = copy.deepcopy(resolved.api)
        profile['target_binding']['return_mapping'][0]['mapping_kind'] = 'converted'
        with self.assertRaisesRegex(builder.ItemInputError, 'adapter'):
            builder.resolve_api_output_ports(profile)
        with self.assertRaises(emitter.MaterializationError):
            emitter.resolved_target_output_contract(profile)

    def test_artifact_requires_real_matching_review(self):
        _, _, path, _, _ = pilot('torch.nn.functional.cosine_embedding_loss')
        with self.assertRaisesRegex(emitter.InputError, 'exact approved'):
            emitter.approved_strategy_review(None, path, load(path))

    def test_repair_review_is_bound_to_exact_parent(self):
        from test_review_strategy_plan import review, blocking_finding
        _, _, path, _, _ = pilot('torch.nn.functional.cosine_embedding_loss')
        parent = load(path)
        record = review('needs_revision', [blocking_finding()])
        record['reviewer_id'] = 'unit_test_fixture'
        record['subject'] = {'strategy_id': parent['identity']['strategy_id'], 'revision_number': 1,
                             'content_hash': builder.canonical_hash(parent), 'relative_path': str(path)}
        rules = ROOT / 'schemas/strategy_plan_human_review_rules.md'
        record['rules_ref'] = {'artifact_id': rules.name, 'artifact_version': '1.1',
                               'content_hash': builder.file_hash(rules), 'relative_path': str(rules)}
        validator = builder.schema_validator(load(ROOT / 'schemas/strategy_plan_review_record.schema.json'), 'review')
        with tempfile.TemporaryDirectory() as temporary:
            review_path = Path(temporary) / 'review.json'
            review_path.write_text(json.dumps(record))
            args = argparse.Namespace(strategy_review=review_path, parent_strategy=path, revision_trigger='manual_review')
            self.assertIn(blocking_finding()['mismatch_summary'], builder.repair_review(args, parent, validator)[0])
            record['subject']['content_hash'] = '0' * 64
            review_path.write_text(json.dumps(record))
            with self.assertRaisesRegex(builder.ItemInputError, 'exact-hash'):
                builder.repair_review(args, parent, validator)

    def test_unsupported_before_llm(self):
        *_, catalog, resolved = pilot('torch.batch_norm_update_stats')
        changed = copy.deepcopy(resolved.spec)
        changed['exploration_plan']['branches'][0]['target_conditions'] = [{'condition_id': 'tc_unsupported', 'predicate': {'predicate_id': 'rank_constraint', 'arguments': {}}, 'role': 'exploration_variable', 'observe_at': ['before_target_api_call'], 'source_refs': []}]
        replaced = builder.ResolvedInputs(spec=changed, api=resolved.api, resolved_api_primitive=resolved.resolved_api_primitive, candidate_primitives=resolved.candidate_primitives, harness_spec_review_ref=resolved.harness_spec_review_ref)
        with self.assertRaisesRegex(builder.ItemInputError, 'Capability gap'):
            builder.capability_preflight(replaced, catalog)

    def test_cli_adopt_and_artifact_full_preflight_no_llm(self):
        spec, review, parent, _, _ = pilot('torch.nn.functional.cosine_embedding_loss')
        with tempfile.TemporaryDirectory(prefix='strategy_preflight_', dir=ROOT / 'tests') as directory:
            command = [sys.executable, '-B', str(ROOT / 'scripts/build_strategy_plan_json.py'),
                '--harness-spec', str(spec), '--harness-spec-review', str(review),
                '--parent-strategy', str(parent), '--strategy-revision', '2', '--revision-trigger', 'catalog_update',
                '--adopt-parent', '--output-root', directory]
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            outcome = json.loads(result.stdout)
            plan = load(outcome['output_path'])
            self.assertEqual(plan['implementation_plan'], load(parent)['implementation_plan'])
            self.assertEqual(plan['schema_version'], '1.3')
            trace = load(plan['source_context']['generation_trace_ref']['relative_path'])
            self.assertEqual(trace['attempts'], [])
            self.assertEqual(trace['materialization_preflight']['status'], 'passed')
            repeated = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertNotEqual(repeated.returncode, 0)
            self.assertIn('Refusing to overwrite immutable Strategy', repeated.stderr)
            self.assertEqual(builder.canonical_hash(load(outcome['output_path'])), builder.canonical_hash(plan))
            command = [sys.executable, '-B', str(ROOT / 'scripts/build_harness_artifact.py'), '--strategy-plan', outcome['output_path'], '--preflight-only', '--output-root', directory + '/artifacts']
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            summary = next(Path(directory).glob('artifacts/run_summaries/*.json'))
            self.assertEqual(load(summary)['results'][0]['status'], 'preflight_passed')
            # Temporary synthetic reviewer exercises exact-hash approval routing;
            # this is not a human approval of an experimental Plan.
            command = [sys.executable, '-B', str(ROOT / 'scripts/review_strategy_plan.py'),
                '--strategy-plan', outcome['output_path'], '--decision', 'approved', '--reviewer', 'unit_test_fixture',
                '--output-root', directory + '/reviews', '--review-artifacts', directory + '/review_rules']
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            strategy_review = json.loads(result.stdout)['output_path']
            api = 'torch.nn.functional.cosine_embedding_loss'
            command = [sys.executable, '-B', str(ROOT / 'scripts/build_strategy_plan_json.py'),
                '--harness-spec', str(ROOT / f'harness_specs/pytorch/{api}/bug_aware_static/hs_pytorch_{api}_bug_aware_static_r4.json'),
                '--harness-spec-review', str(ROOT / f'harness_spec_reviews/pytorch/{api}/bug_aware_static/hs_pytorch_{api}_bug_aware_static_r4__review_r1.json'),
                '--canonical-default-strategy', outcome['output_path'], '--canonical-default-strategy-review', strategy_review,
                '--dry-run', '--output-root', directory + '/static']
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('canonical_default_strategy_view', result.stdout)
            self.assertIn('"status": "dry_run"', result.stdout)


if __name__ == '__main__':
    unittest.main()
