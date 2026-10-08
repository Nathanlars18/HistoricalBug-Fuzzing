"""Atomic observations for Spec v2.2; never infer joint activation or validity."""
from __future__ import annotations

PHASES = {'pre_call_observation': 'before_target_api_call',
          'post_call_observation': 'after_target_api_call'}


def measurements(spec, artifact, snapshot, controller):
    index, counts = controller.event_index(artifact, snapshot)
    slots = {item['emitted_segment_id']: item['template_slot']
             for item in artifact.get('materialization_map', [])}

    def linked_sites(branch_id, kind, element_type, element_id, phase=None):
        sites = []
        for item in index.get((branch_id, kind), []):
            if not any(ref.get('ref_type') == element_type and ref.get('ref_id') == element_id
                       for ref in item.get('trace_refs', [])):
                continue
            slot = slots.get(item.get('source_owner', {}).get('owner_id'))
            actual_phase = PHASES.get(slot)
            if phase is None or actual_phase == phase:
                sites.append(item)
        return sites

    rows = []
    for branch in spec['exploration_plan']['branches']:
        branch_id = branch['branch_id']
        refs = []
        def total(kind, **kwargs):
            value, bindings = controller.event_total(index, counts, branch_id, kind, **kwargs)
            refs.extend(bindings)
            return value
        selected = total('branch_entered', exactly_one=True)
        reached = total('target_api_reached', require_present=True, aggregation='maximum')
        completed = total('target_api_completed', require_present=True, aggregation='minimum')
        rejected = total('input_rejected')
        exception_sites = index.get((branch_id, 'target_api_exception'), [])
        exceptions = max((counts[item['runtime_site_id']] for item in exception_sites), default=None)
        refs.extend(item['instrumentation_binding_id'] for item in exception_sites)
        if max([reached, completed, rejected, *( [] if exceptions is None else [exceptions])]) > selected or (exceptions is not None and completed + exceptions > reached):
            raise controller.CounterConsistencyError('Branch target/rejection counters are inconsistent')
        conditions = []
        for condition in branch['target_conditions']:
            for phase in condition['observe_at']:
                row = {'condition_id': condition['condition_id'], 'role': condition['role'],
                       'observe_at': phase, 'state': 'available', 'checked': None, 'true': None,
                       'unevaluable': None, 'error': None, 'rate': None, 'binding_refs': []}
                for field, kind in [('checked', 'activation_checked'), ('true', 'activation_true'),
                                    ('unevaluable', 'activation_unevaluable'), ('error', 'activation_check_error')]:
                    sites = linked_sites(branch_id, kind, 'target_condition', condition['condition_id'], phase)
                    if len(sites) != 1:
                        row['state'] = 'missing_or_ambiguous_instrumentation'
                        continue
                    row[field] = counts[sites[0]['runtime_site_id']]
                    row['binding_refs'].append(sites[0]['instrumentation_binding_id'])
                if row['state'] == 'available':
                    if row['true'] > row['checked'] or row['checked'] + row['unevaluable'] + row['error'] > selected:
                        raise controller.CounterConsistencyError('Atomic condition counters are inconsistent')
                    if row['error']:
                        row['state'] = 'checker_error'
                    elif row['checked'] == 0 and row['unevaluable']:
                        row['state'] = 'unevaluable'
                    if row['checked']:
                        row['rate'] = row['true'] / row['checked']
                refs.extend(row['binding_refs'])
                conditions.append(row)
        checks = []
        for check in branch['behavior_checks']:
            sites = linked_sites(branch_id, 'oracle_evaluated', 'behavior_check', check['check_id'])
            checks.append({'check_id': check['check_id'], 'requirement_level': check['requirement_level'],
                          'state': 'available' if len(sites) == 1 else 'missing_or_ambiguous_instrumentation',
                          'opportunities': completed,
                          'evaluated': counts[sites[0]['runtime_site_id']] if len(sites) == 1 else None,
                          'binding_refs': [s['instrumentation_binding_id'] for s in sites]})
            if len(sites) == 1:
                refs.append(sites[0]['instrumentation_binding_id'])
                if checks[-1]['evaluated'] > completed:
                    raise controller.CounterConsistencyError('Behavior-check counts exceed completed target calls')
        # Legacy scalar fields are not joint summaries. A selected atomic signal is
        # projected into them only by diagnose(); all raw atoms remain in the record.
        values = {'branch_selected_count': selected, 'target_reached_count': reached,
                  'input_rejected_count': rejected, 'target_exception_count': exceptions,
                  'target_exception_observation_state': 'available' if exception_sites else 'missing_instrumentation',
                  'activation_required': False, 'activation_checked_count': None,
                  'activation_true_count': None, 'activation_unevaluable_count': None,
                  'activation_check_error_count': None, 'oracle_required': False,
                  'oracle_opportunity_count': None, 'oracle_evaluated_count': None,
                  'condition_measurements': conditions, 'behavior_check_measurements': checks}
        rows.append({'branch_id': branch_id, 'measurements': values,
                     'instrumentation_binding_refs': sorted(set(refs))})
    return rows


def diagnose(measured, policy, legacy_diagnose):
    import copy
    values = copy.deepcopy(measured['measurements'])
    evidence = policy['evidence_thresholds']
    minimum = evidence['minimum_branch_activation_attempts']
    atoms = values['condition_measurements']
    usable = [a for a in atoms if a['state'] == 'available' and a['checked'] >= minimum]
    rare = policy['diagnosis_thresholds']['activation_rare']['maximum_activation_rate_exclusive']
    # One atomic trigger, with a stable tie-break; neither AND nor OR is inferred.
    usable.sort(key=lambda a: (0 if a['true'] == 0 else 1 if a['rate'] < rare else 2,
                               a['condition_id'], a['observe_at']))
    trigger = usable[0] if usable else None
    if trigger is not None:
        values.update(activation_required=True, activation_checked_count=trigger['checked'],
                      activation_true_count=trigger['true'], activation_unevaluable_count=trigger['unevaluable'],
                      activation_check_error_count=trigger['error'])
    checks = values['behavior_check_measurements']
    required = [c for c in checks if c['requirement_level'] == 'required']
    ready = [c for c in required if c['state'] == 'available' and
             c['opportunities'] >= evidence['minimum_oracle_opportunities']]
    if ready:
        check = min(ready, key=lambda c: (c['evaluated'] / c['opportunities'], c['check_id']))
        values.update(oracle_required=True, oracle_opportunity_count=check['opportunities'],
                      oracle_evaluated_count=check['evaluated'])
    projected = {**measured, 'measurements': values}
    result = legacy_diagnose(projected, policy)
    statuses = set([result['primary_status'], *result['supporting_statuses']])
    statuses.discard('branch_no_detected_bottleneck')
    if atoms and not usable:
        if any(a['state'] == 'available' for a in atoms):
            statuses.add('branch_under_sampled')
        else:
            statuses.add('branch_activation_unevaluable')
    if any(c['state'] != 'available' for c in required):
        statuses.add('branch_oracle_unevaluable')
    elif required and not ready:
        statuses.add('branch_under_sampled')
    order = ('branch_under_sampled', 'branch_rejection_dominated', 'branch_target_not_observed',
             'branch_activation_unevaluable', 'branch_activation_absent', 'branch_activation_rare',
             'branch_oracle_unevaluable', 'branch_no_detected_bottleneck')
    ordered = [name for name in order if name in statuses] or ['branch_no_detected_bottleneck']
    result['primary_status'], result['supporting_statuses'] = ordered[0], ordered[1:]
    result['trigger_condition'] = None if trigger is None else {
        'branch_id': measured['branch_id'], 'condition_id': trigger['condition_id'],
        'role': trigger['role'], 'observe_at': trigger['observe_at']}
    # An unobservable-only branch is neither a recipient nor a donor; one missing
    # atom does not disable independent, usable atoms in the same branch.
    result['budget_evidence_usable'] = not (atoms and not usable and
        not any(a['state'] == 'available' for a in atoms)) and not any(c['state'] != 'available' for c in required)
    result['budget_recipient_evidence_usable'] = result['budget_evidence_usable']
    result['budget_donor_evidence_usable'] = result['budget_evidence_usable'] and 'branch_oracle_unevaluable' not in statuses
    return result
