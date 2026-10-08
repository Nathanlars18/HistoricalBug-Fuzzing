"""Conservative, emitter-matched input domains; not universal API contracts.

Unknown facts are capability gaps, never evidence for accepting a plan. Domains
describe this bounded generator only, not statistical reachability in a run.
"""
from __future__ import annotations

import math
from typing import Any


def parameters(step: dict[str, Any]) -> dict[str, Any]:
    return {b['parameter_id']: b['binding_value'] for b in step['parameter_bindings']
            if b['binding_kind'] == 'literal'}


def shape_variants(d: dict[str, Any]) -> list[list[tuple]]:
    if d.get('kind') != 'tensor':
        return []
    return d.get('shape_alternatives', [d['shape']] if 'shape' in d else [])


def shape_pairs(left: dict[str, Any], right: dict[str, Any]) -> list[tuple[list, list]]:
    """Reference transforms preserve the original rank selector correlation."""
    l, r = shape_variants(left), shape_variants(right)
    if left.get('choice_source') is not None and left.get('choice_source') == right.get('choice_source'):
        return list(zip(l, r))
    return [(a, b) for a in l for b in r]


def infer_domains(steps: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    domains: dict[str, dict[str, Any]] = {'none': {'kind': 'none'}}
    for step in steps:
        pid, p = step['primitive_id'], parameters(step)
        inputs = {b['port_id']: b['value_ref'] for b in step['input_bindings']}
        d: dict[str, Any] = {'kind': 'unknown'}
        if pid == 'construct_tensor_with_rank_range':
            lo, hi = p.get('minimum_dimension', 0), p.get('max_dimension', 4)
            d = {'kind': 'tensor', 'shape_alternatives': [
                [(lo, hi, (step['step_id'], i)) for i in range(rank)]
                for rank in range(p['minimum_rank'], p['maximum_rank'] + 1)],
                'choice_source': step['step_id'], 'dtype': p.get('dtype_policy'), 'fill': p.get('fill_policy')}
        elif pid in {'construct_tensor_from_fuzz', 'construct_tensor_with_constraints'}:
            hi, lo = p.get('max_dimension', 4), p.get('minimum_dimension', 0)
            shape = [-1, -1] if pid == 'construct_tensor_from_fuzz' else p.get('shape_template', [])
            d = {'kind': 'tensor', 'shape': [
                (lo, hi, (step['step_id'], i)) if n == -1 else (n, n, ('constant', n))
                for i, n in enumerate(shape)], 'dtype': p.get('dtype_policy'),
                'fill': p.get('fill_policy', 'fuzz_numeric')}
        elif pid == 'construct_tensor_from_reference':
            ref = domains.get(inputs.get('reference'), {})
            if ref.get('kind') == 'tensor':
                policy = p.get('shape_policy')
                shapes = []
                for original in shape_variants(ref):
                    shape = list(original)
                    if policy == 'drop_last_dimension':
                        shape = shape[:-1]
                    elif policy != 'same_shape':
                        axis = p.get('reference_axis', 0) if policy == 'selected_dimension' else 0
                        shape = [shape[axis]] if 0 <= axis < len(shape) else [(0, 0, ('constant', 0))]
                    shapes.append(shape)
                d = {'kind': 'tensor', 'dtype': p.get('dtype_policy'),
                     'fill': p.get('fill_policy')}
                if 'shape_alternatives' in ref:
                    d.update(shape_alternatives=shapes, choice_source=ref['choice_source'])
                else:
                    d['shape'] = shapes[0]
        elif pid == 'select_optional_tensor_from_fuzz':
            d = {'kind': 'optional_tensor', 'present': domains.get(inputs.get('tensor'), {}), 'allows_none': True}
        elif pid in {'construct_integer_from_fuzz', 'construct_floating_from_fuzz'}:
            d = {'kind': 'scalar', 'range': (p.get('minimum'), p.get('maximum'))}
        elif pid == 'construct_boolean_from_fuzz':
            d = {'kind': 'scalar', 'range': (False, True)}
        for b in step['output_bindings']:
            if b['port_id'] in {'tensor', 'value', 'optional_value'}:
                domains[b['value_id']] = d
    return domains


def numel_range(d: dict[str, Any]) -> tuple[int, int] | None:
    if d.get('kind') != 'tensor':
        return None
    variants = shape_variants(d)
    return (min(math.prod(axis[0] for axis in shape) for shape in variants),
            max(math.prod(axis[1] for axis in shape) for shape in variants))

def meaningful_fuzz_domain(d: dict[str, Any]) -> bool | None:
    if d.get('kind') == 'tensor':
        return (property_can_vary(d, 'shape')
                or (numel_range(d)[1] > 0 and d.get('fill') in {'fuzz_numeric', 'fuzz_sign'}))
    if d.get('kind') == 'optional_tensor':
        return True  # None versus defined Tensor is a real input distinction.
    if d.get('kind') == 'scalar':
        return d['range'][0] != d['range'][1]
    if d.get('kind') == 'none':
        return False
    return None


def property_can_vary(d: dict[str, Any], prop: str) -> bool:
    if d.get('kind') != 'tensor':
        return False
    if prop == 'shape':
        shapes = shape_variants(d)
        return len({len(s) for s in shapes}) > 1 or any(lo != hi for s in shapes for lo, hi, _ in s)
    if prop == 'rank':
        return len({len(s) for s in shape_variants(d)}) > 1
    if prop == 'numel':
        r = numel_range(d)
        return r is not None and r[0] != r[1]
    # Dtype, strides and device remain fixed in this bounded adapter.
    return False


def zero_numel_form(predicate: dict[str, Any]) -> bool:
    p, a = predicate['predicate_id'], predicate['arguments']
    return a.get('property_ref') == 'numel' and (
        (p == 'property_relation' and a.get('operator') == 'equals' and a.get('value') == 0)
        or (p == 'range_constraint' and a.get('lower_bound') == 0 and a.get('upper_bound') == 0
            and a.get('lower_inclusive') is True and a.get('upper_inclusive') is True))

def output_check_parameters(predicate: dict[str, Any]) -> dict[str, Any] | None:
    a = predicate['arguments']
    if predicate['predicate_id'] != 'property_relation' or a.get('operator') != 'equals':
        return None
    prop, value = a.get('property_ref'), a.get('value')
    if prop in {'rank', 'numel'} and isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return {'check_kind': prop + '_equals', 'expected_integer': value}
    if prop == 'dtype' and value == 'int64':
        return {'check_kind': 'dtype_is_int64'}
    if prop == 'shape' and isinstance(value, list) and len(value) <= 4 and all(isinstance(n, int) and not isinstance(n, bool) and 0 <= n <= 16 for n in value):
        return {'check_kind': 'shape_equals', 'expected_shape': value}
    if prop == 'all_zero' and value is True:
        return {'check_kind': 'all_zero'}
    return None

def dimension_equality_form(predicate: dict[str, Any]) -> bool:
    a = predicate['arguments']
    return (predicate['predicate_id'] == 'cross_subject_relation' and a.get('relation') == 'equals'
            and a.get('left_property_ref') == a.get('right_property_ref') == 'dimension_size'
            and all(isinstance(a.get(k), int) and not isinstance(a.get(k), bool) and 0 <= a[k] <= 3
                    for k in ('left_axis', 'right_axis')))


def exploration_domain_error(predicate: dict[str, Any], subjects: dict[str, dict[str, Any]]) -> str | None:
    a = predicate['arguments']
    if predicate['predicate_id'] == 'property_relation' and a.get('property_ref') == 'rank' and a.get('operator') == 'equals':
        ranks = {len(s) for s in shape_variants(subjects.get(a['subject_ref'], {}))}
        return None if a.get('value') in ranks and len(ranks) > 1 else 'rank exploration requires both matching and nonmatching ranks'
    if zero_numel_form(predicate):
        r = numel_range(subjects.get(a['subject_ref'], {}))
        if r is None or not (r[0] == 0 and r[1] > 0):
            return 'numel == 0 exploration requires both zero and nonzero possibilities; varying fill alone is insufficient'
        return None
    if predicate['predicate_id'] == 'cross_subject_relation':
        left, right = subjects.get(a['left_subject_ref'], {}), subjects.get(a['right_subject_ref'], {})
        prop = a.get('left_property_ref')
        if prop != a.get('right_property_ref') or prop not in {'shape', 'numel', 'rank'}:
            return 'unsupported cross-subject property domain'
        if left.get('kind') != 'tensor' or right.get('kind') != 'tensor':
            return 'unknown tensor relationship domain'
        pairs = shape_pairs(left, right)
        if prop == 'rank':
            outcomes = {len(l) == len(r) for l, r in pairs}
            return None if outcomes == {False, True} else 'rank relation is invariant in the generated domain'
        if pairs and all(l == r for l, r in pairs):
            return 'reference-derived shapes make this relation invariant'
        if not (property_can_vary(left, prop) or property_can_vary(right, prop)):
            return 'referenced property is fixed despite varying tensor contents'
        if prop == 'shape':
            if not any(len(l) == len(r) and all(max(a[0], b[0]) <= min(a[1], b[1]) for a, b in zip(l, r)) for l, r in pairs):
                return 'disjoint dimension domains make shape equality impossible'
        elif prop == 'numel':
            l, r = numel_range(left), numel_range(right)
            if l is None or r is None or max(l[0], r[0]) > min(l[1], r[1]):
                return 'disjoint numel domains make equality impossible'
        return None
    return 'no property-specific exploration domain proof for this predicate form'


def ordinary_recipe_errors(branch: dict[str, Any], domains: dict[str, dict[str, Any]],
                           recipe: dict[str, Any], target: dict[str, Any]) -> list[str]:
    """Only called for expected_valid branches; boundary exploration is untouched."""
    bound = {b['port_id']: b['value_ref'] for b in target['input_bindings']}
    errors = []
    for rule in recipe.get('rules', []):
        port = rule['port_id']
        d = domains.get(bound.get(port), {'kind': 'unknown'})
        if rule.get('allow_none') and d.get('kind') == 'none':
            continue
        if rule.get('allow_none') and d.get('kind') == 'optional_tensor':
            d = d['present']
        if d.get('kind') != 'tensor':
            errors.append(f'{port}: no bounded Tensor-domain proof for ordinary recipe')
            continue
        if 'rank' in rule and any(len(s) != rule['rank'] for s in shape_variants(d)):
            errors.append(f'{port}: ordinary recipe requires rank {rule["rank"]}')
        if rule.get('nonempty') and numel_range(d)[0] == 0:
            errors.append(f'{port}: ordinary recipe requires nonempty dimensions (minimum_dimension=1)')
        if 'dtype' in rule and d['dtype'] != rule['dtype']:
            errors.append(f'{port}: recipe dtype differs')
        if 'shape_from' in rule:
            ref = domains.get(bound.get(rule['shape_from']), {})
            expected = ref.get('shape')
            if expected is not None and 'axis' in rule:
                expected = [expected[rule['axis']]] if rule['axis'] < len(expected) else None
            if expected is None or d['shape'] != expected:
                errors.append(f'{port}: shape must derive from {rule["shape_from"]}' + (f' axis {rule["axis"]}' if 'axis' in rule else ''))
        if 'fill' in rule and d.get('fill') != rule['fill']:
            errors.append(f'{port}: recipe label domain requires {rule["fill"]}')
    return errors


def companion_relation_errors(branch: dict[str, Any], domains: dict[str, dict[str, Any]],
                              target: dict[str, Any], rules: list[dict[str, Any]]) -> list[str]:
    """Reject only a proved wholly incompatible, unrequested auxiliary relation.

    Mixed valid/invalid domains stay legal; a supported targeted invalid case is
    also legal. This is not a universal validity filter for boundary branches.
    """
    bound = {b['port_id']: b['value_ref'] for b in target['input_bindings']}
    errors = []
    for rule in rules:
        predicates = [c['predicate'] for c in branch.get('target_conditions', []) + branch.get('branch_constraints', [])]
        subject = rule['dependent_subject_ref']
        explicit = any((p['arguments'].get('property_ref') in {'rank', 'shape'} and p['arguments'].get('subject_ref') == subject)
                       or (p['arguments'].get('left_property_ref') in {'rank', 'shape'} and subject in
                           {p['arguments'].get('left_subject_ref'), p['arguments'].get('right_subject_ref')}) for p in predicates)
        if explicit:
            continue
        ref = domains.get(bound.get(rule['reference_port']), {})
        dep = domains.get(bound.get(rule['dependent_port']), {})
        pairs = shape_pairs(ref, dep)
        allowed = {tuple(p) for p in rule['allowed_rank_pairs']}
        if pairs and not any((len(l), len(r)) in allowed for l, r in pairs):
            errors.append(f"{rule['rule_id']}: auxiliary rank relation is wholly incompatible and not an explicit Spec target; it masks the explored input relation")
    return errors
