"""Python adaptation of jomjol/AI-on-the-edge-device pointer correction.

Source: ClassFlowCNNGeneral.cpp, revision 708129ba779e233b6fe67ace663bada31888d2ad.
Authors: jomjol and upstream contributors. Modified for HA AI Studio.
Dual Use License v1.0; see LICENSE.md and THIRD_PARTY.md.
"""
import math


def rounded(value):
    # C++ round: half away from zero (inputs here are nonnegative).
    return math.floor(value + .5)


def analog(number, predecessor=-1):
    if predecessor < 0:
        return math.floor(number)
    low, high = number - .3, number + .3
    if math.floor(high) != math.floor(low):
        if predecessor <= 3:
            return math.floor(high) % 10
        if predecessor >= 7:
            return math.floor(low) % 10
    return math.floor(number) % 10


def analog_to_digit(number, lower_raw, lower_digit, transition=9.2):
    fraction = math.floor(number * 10) % 10
    up = fraction >= 8 or (lower_digit <= 4 and fraction >= 6)
    result = rounded(number) % 10 if up else math.trunc(number) % 10
    if lower_digit >= 6 and (lower_raw > transition or lower_raw <= .2) and up:
        result = (result - 1) % 10
    return result


def hybrid(number, lower_raw=-1, lower_digit=-1, lower_analog=False, transition=9.2):
    if lower_digit < 0:
        return math.trunc(rounded(number * 100) / 100)
    if lower_analog:
        return analog_to_digit(number, lower_raw, lower_digit, transition)
    fraction = math.floor(number * 10) % 10
    integer = math.floor(number) % 10
    if .7 <= lower_raw <= 9.3:
        return rounded(number) % 10 if fraction <= 3 or fraction >= 7 else math.trunc(number) % 10
    if lower_digit <= 1:
        return (integer + 1) % 10 if fraction > 5 else integer
    return integer if lower_raw <= 9.7 or fraction >= 4 else (integer - 1) % 10


def combine(digits, pointers, shift=0, extended=False, transition=9.2):
    """Inputs are ordered most significant first, like upstream ROI lists."""
    if not digits and not pointers:
        raise ValueError('No reading regions configured.')
    if any(not math.isfinite(v) or not 0 <= v < 10 for v in digits + pointers):
        raise ValueError('A region has no valid reading.')
    tail = ''
    predecessor = -1
    for number in reversed(pointers):
        predecessor = analog(number, predecessor)
        tail = str(predecessor) + tail
    lower_raw = pointers[0] if pointers else -1
    for index in range(len(digits) - 1, -1, -1):
        predecessor = math.floor(digits[index]) if extended and not pointers and index == len(digits)-1 else hybrid(digits[index], lower_raw, predecessor, bool(pointers) and index == len(digits) - 1, transition)
        if not 0 <= predecessor < 10:
            raise ValueError('Digit rollover is ambiguous.')
        tail = str(predecessor) + tail
        lower_raw = digits[index]
    decimals = len(pointers)
    if extended:
        number = pointers[-1] if pointers else digits[-1]
        tail += str(math.floor(number * 10) % 10)
        decimals += 1
    from decimal import Decimal
    return str(Decimal(tail) * (Decimal(10) ** (shift - decimals)))
