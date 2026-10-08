#!/usr/bin/env python3
"""Opt-in pinned-image compilation/smoke of fixtures; never calls an LLM.

Fixtures are not approved research Plans or experiment results. This checks
emitted C++ and exception classification only, not detection effectiveness.
"""
from __future__ import annotations

import copy
import json
import subprocess
import tempfile
from pathlib import Path

from test_strategy_preflight import ROOT, pilot, fix_batch, static_fixture, load, builder, emitter

IMAGE = 'sha256:10968a7f565bb6c1fa008d3a5800af46a8085de7d880c3db3751c287d29865c8'


def main():
    config = emitter.load_compile_config(Path('runtime/flashfuzz_2_10/harness_compile_profile.json'))
    results = []
    with tempfile.TemporaryDirectory(prefix='runtime_smoke_', dir=ROOT / 'tests') as temporary:
        for api, fixture in [('torch.batch_norm_update_stats', 'ordinary'),
                             ('torch.nn.functional.cosine_embedding_loss', 'ordinary'),
                             ('torch.batch_norm_update_stats', 'invalid_stats_exception'),
                             ('torch.batch_norm_update_stats', 'ordinary_optional'),
                             ('torch.nn.functional.cosine_embedding_loss', 'ordinary_scalars'),
                             ('torch.nn.functional.cosine_embedding_loss', 'static_rank_relation')]:
            _, _, parent, catalog, resolved = pilot(api)
            record = copy.deepcopy(load(parent))
            plan = record['implementation_plan']
            if fixture == 'static_rank_relation':
                plan, resolved, catalog = static_fixture(api)
            if api == 'torch.batch_norm_update_stats' and fixture != 'invalid_stats_exception':
                plan = fix_batch(plan)
            if fixture == 'ordinary_optional':
                steps = plan['branch_strategies'][0]['steps']
                target = steps.pop()
                cursor = steps[-1]['output_bindings'][1]['value_id']
                for index, port in enumerate(('binding_param_001_running_mean', 'binding_param_002_running_var')):
                    old = next(b['value_ref'] for b in target['input_bindings'] if b['port_id'] == port)
                    value, next_cursor = f'optional_stats_{index}', f'optional_cursor_{index}'
                    steps.append({'step_id': f'step_optional_{index}', 'primitive_id': 'select_optional_tensor_from_fuzz',
                        'template_slot': 'pre_call_transform', 'input_bindings': [
                            {'port_id': p, 'value_ref': v} for p, v in {'tensor': old, 'data': 'data', 'size': 'size', 'cursor': cursor}.items()],
                        'parameter_bindings': [], 'output_bindings': [{'port_id': 'optional_value', 'value_id': value}, {'port_id': 'next_cursor', 'value_id': next_cursor}]})
                    next(b for b in target['input_bindings'] if b['port_id'] == port)['value_ref'] = value
                    cursor = next_cursor
                steps.append(target)
            if fixture == 'ordinary_scalars':
                steps = plan['branch_strategies'][0]['steps']
                target = steps.pop()
                cursor = steps[-1]['output_bindings'][1]['value_id']
                for name, primitive, low, high, port in (
                    ('margin', 'construct_floating_from_fuzz', -1.0, 1.0, 'binding_param_003_margin'),
                    ('reduction', 'construct_integer_from_fuzz', 0, 2, 'binding_param_004_reduction')):
                    value, next_cursor = f'fuzz_{name}', f'cursor_{name}'
                    steps.append({'step_id': f'step_{name}', 'primitive_id': primitive, 'template_slot': 'input_construction',
                        'input_bindings': [{'port_id': p, 'value_ref': v} for p, v in {'data': 'data', 'size': 'size', 'cursor': cursor}.items()],
                        'parameter_bindings': [{'parameter_id': p, 'binding_kind': 'literal', 'binding_value': v} for p, v in {'minimum': low, 'maximum': high}.items()],
                        'output_bindings': [{'port_id': 'value', 'value_id': value}, {'port_id': 'next_cursor', 'value_id': next_cursor}]})
                    target['input_bindings'].append({'port_id': port, 'value_ref': value})
                    cursor = next_cursor
                steps.append(target)
            builder.materialize_failure_handlers(plan, resolved)
            record['implementation_plan'] = plan
            if fixture != 'invalid_stats_exception':
                builder.validate_materialized_plan(plan, resolved, catalog)
            source, materialization, events = emitter.materialize_strategy(
                emitter.ResolvedInputs(record, resolved.spec, catalog, resolved.api, {}),
                emitter.allocate_selector_ranges(resolved.spec['exploration_plan']['branches']),
                ROOT / 'templates/libfuzzer_harness_v1.cpp.in')
            source = emitter.finalize_source(source, 'smoke_fixture', '0' * 64, len(events))
            directory = Path(temporary).resolve() / (api.replace('.', '_') + '_' + fixture)
            directory.mkdir()
            (directory / 'main.cpp').write_text(source)
            compile_check = emitter.compile_harness(config, directory, directory,
                ROOT / 'runtime/harness_instrumentation.h', ROOT / 'runtime/harness_instrumentation.cpp')
            if compile_check['status'] != 'passed':
                diagnostics = (directory / 'compile_diagnostics.txt').read_text()
                raise RuntimeError(f'{api}/{fixture} compile failed: {diagnostics}')
            # Same corpus bytes; no historical trigger inputs. Full stats shapes
            # are intentionally invalid only in the exception-classification fixture.
            cases = [('seed', bytes([0, 1, 1, 8] + [1, 1, 8] * 3), fixture == 'invalid_stats_exception')]
            if fixture == 'static_rank_relation':
                # General witnesses, not historical trigger inputs: rank-1,
                # rank-2, empty, and an intentionally explored rank mismatch.
                cases = [('rank1', bytes([255, 0, 2, 8, 0, 2, 8, 1]), False),
                         ('rank2', bytes([255, 1, 2, 3, 8, 1, 2, 3, 8, 1]), False),
                         ('empty', bytes([255, 0, 0, 8, 0, 0, 8, 1]), False),
                         ('rank_mismatch', bytes([255, 0, 2, 8, 1, 2, 3, 8, 1]), True)]
            case_results = []
            for case_name, payload, expected_exception in cases:
                seed = directory / case_name
                seed.write_bytes(payload)
                command = ['docker', 'run', '--rm', '-v', f'{directory}:/artifact',
                    '-e', f'HBFG_METRICS_PATH=/artifact/{case_name}_metrics.json', '-e', 'HBFG_METRICS_SNAPSHOT_INTERVAL=1',
                    IMAGE, '/artifact/harness_binary', f'/artifact/{case_name}', '-runs=1']
                run = subprocess.run(command, capture_output=True, text=True, timeout=60)
                if run.returncode != 0:
                    raise RuntimeError(f'Smoke fixture failed: {fixture}/{case_name}: {run.stderr}')
                exception = 'HBFG_TARGET_API_EXCEPTION=' in run.stderr
                if exception != expected_exception:
                    raise RuntimeError(f'Unexpected target exception status: {api}/{fixture}/{case_name}: {run.stderr}')
                case_results.append({'case': case_name, 'caught_target_exception': exception})
            results.append({'api': api, 'fixture': fixture, 'compile': 'passed',
                            'exit_code': 0, 'cases': case_results,
                            'image_id': IMAGE})
            print(json.dumps(results[-1]), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
