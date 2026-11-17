#!/usr/bin/env python3
"""Require exactly one recorded attempt for every frozen case/repetition in a round. No cluster access."""
import collections, csv, json, sys


def check(round_id, cases, attempts):
    expected = {(c['case_id'], rep) for c in cases for rep in (1, 2, 3)}
    actual = collections.Counter((a.get('case'), a.get('rep')) for a in attempts)
    duplicates = [key for key, count in actual.items() if count != 1]
    runs = [a.get('run') for a in attempts]
    problems = []
    if set(actual) != expected: problems.append(f'missing={sorted(expected-set(actual))}, unexpected={set(actual)-expected}')
    if duplicates: problems.append(f'duplicate case/repetition: {duplicates}')
    if None in runs or len(set(runs)) != len(runs): problems.append('missing or duplicate run identifiers')
    if any(a.get('round') != round_id for a in attempts): problems.append('wrong round identifier')
    if problems: raise ValueError('; '.join(problems))
    return len(expected)


if __name__ == '__main__':
    round_id = sys.argv[1]
    try:
        cases = list(csv.DictReader(open('cases/cases.csv')))
        attempts = [json.loads(line) for line in open(f'results/attempts-{round_id}.jsonl')]
        count = check(round_id, cases, attempts)
    except (ValueError, OSError) as e: sys.exit(f'incomplete round {round_id}: {e}')
    print(f'{round_id}: {count} unique attempts; all cases and repetitions present')
