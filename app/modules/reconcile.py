from collections import Counter

from app.intake.schema import valid_identifier


def release(intake, cases):
    """按批组归属隔离行，判定各组可否签发。

    列数错乱的行字段对不齐、批组标识非法的行认不出批组，整单待查；
    其余隔离行按批组名归到牵涉的组（包括单外批组），沾行组暂缓。
    """
    holds, unattributed = {}, []
    for row in intake.get('isolation', []):
        case = row.get('case') or ''
        if row['reason'] != 'COLUMN_COUNT' and valid_identifier(case):
            holds.setdefault(case, []).append(row)
        else:
            unattributed.append(row)
    blocked = bool(unattributed)
    groups = {}
    for case in cases:
        name = case.get('case')
        if name is None:
            continue
        groups[name] = dict(releasable=case['status'] == 'READY' and name not in holds and not blocked,
                            holds=holds.get(name, []))
    return dict(blocked=blocked, unattributed=unattributed, holds=holds, cases=groups)


def balance(intake, cases):
    accounted = intake['accepted'] + intake['rejected'] + intake['blank'] + intake['repeated']
    status = Counter(case['status'] for case in cases)
    ready = status.pop('READY', 0)
    observed = sum(len(case['records']) for case in cases)
    return dict(input=intake['input'], accepted=intake['accepted'], isolated=intake['rejected'],
                ignored=intake['blank'] + intake['repeated'], accounted=accounted,
                balanced=accounted == intake['input'] and observed == intake['accepted'],
                ready=ready, pending=len(cases)-ready, issues=dict(sorted(status.items())),
                releasable=bool(cases) and ready==len(cases) and not intake['rejected'] and accounted==intake['input'] and observed==intake['accepted'],
                release=release(intake, cases))
