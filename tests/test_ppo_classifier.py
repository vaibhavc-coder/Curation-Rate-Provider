"""Unit tests for explainable PPO Network Classifier.

Tests specific edge cases, false-positive guards, glued tokens, conflicts, and metal tiers.
"""

import pytest
from ptd.ppo_classifier import classify_plan_name


def test_explicit_ppo():
    res = classify_plan_name("CA L CUS PPO 15/250/20% RAP")
    assert res.label == "PPO"
    assert res.in_ppo_network is True
    assert res.confidence >= 0.95
    assert "RULE_EXPLICIT_PPO" in res.rule_ids


def test_glued_ppo():
    res = classify_plan_name("CA L CUSPPO 15/250/20% RAP")
    assert res.label == "PPO"
    assert res.in_ppo_network is True
    assert "RULE_GLUED_PPO" in res.rule_ids


def test_metal_tier_ppo_without_ca_prefix():
    res = classify_plan_name("Gold PPO 500/20", market_type="group")
    assert res.label == "PPO"
    assert res.in_ppo_network is True
    assert "RULE_METAL_TIER" in res.rule_ids


def test_false_positive_guard_depot():
    # DEPOT should not trigger EPO
    res = classify_plan_name("DEPOT WORKERS BENEFIT PLAN")
    assert res.label == "Unknown"
    assert res.in_ppo_network is False
    assert "RULE_GUARD_DEPOT" in res.rule_ids
    assert "RULE_EXPLICIT_EPO" not in res.rule_ids


def test_false_positive_guard_post_doc():
    # POST DOC should not trigger POS
    res = classify_plan_name("CA L CUS PPO UC POST DOC")
    assert res.label == "PPO"
    assert res.in_ppo_network is True
    assert "RULE_GUARD_POST_DOC" in res.rule_ids
    assert "RULE_EXPLICIT_POS" not in res.rule_ids


def test_explicit_hmo():
    res = classify_plan_name("CA L CUS HMO 20/500A/2500")
    assert res.label == "HMO"
    assert res.in_ppo_network is False
    assert res.confidence == 1.0
    assert "RULE_EXPLICIT_HMO" in res.rule_ids


def test_explicit_pos():
    res = classify_plan_name("CA L CUS POS COUNTY OF SANTA CLARA")
    assert res.label == "POS"
    assert res.in_ppo_network is False
    assert "RULE_EXPLICIT_POS" in res.rule_ids


def test_conflict_ppo_and_epo():
    res1 = classify_plan_name("CA L CUS PPO CA IRONWORKERS FWP EPO$15")
    assert res1.label == "Conflict"
    assert res1.in_ppo_network is False
    assert "RULE_CONFLICT_NETWORK" in res1.rule_ids

    res2 = classify_plan_name("CA L CUS PPO SACRAMENTO CITY USD- EPO")
    assert res2.label == "Conflict"
    assert res2.in_ppo_network is False
    assert "RULE_CONFLICT_NETWORK" in res2.rule_ids

    res3 = classify_plan_name("CA L CUS PPO CA IRONWORKERS FWP-EPO$10")
    assert res3.label == "Conflict"
    assert res3.in_ppo_network is False


def test_unknown_eoa():
    res = classify_plan_name("CA L CUS CBA EOA Ironworkers FWP")
    assert res.label == "Unknown"
    assert res.in_ppo_network is False
    assert "RULE_EOA_PRODUCT" in res.rule_ids
    assert "EOA represents Health Net Elect Open Access" in res.exclusion_reason


def test_other_unknown_mex():
    res = classify_plan_name("CA L SAL Mex 5/0/1500")
    assert res.label == "Unknown"
    assert res.in_ppo_network is False
    assert "RULE_NO_NETWORK_WORD" in res.rule_ids


# Follow-up tests:
def test_conflict_ppo_and_hmo():
    res = classify_plan_name("CA L CUS PPO HMO SELECT")
    assert res.label == "Conflict"
    assert res.in_ppo_network is False
    assert "RULE_CONFLICT_NETWORK" in res.rule_ids


def test_conflict_ppo_and_pos():
    res = classify_plan_name("CA L CUS PPO/POS ADVANTAGE")
    assert res.label == "Conflict"
    assert res.in_ppo_network is False
    assert "RULE_CONFLICT_NETWORK" in res.rule_ids


def test_ppo_inside_longer_word_guard():
    # HIPPO or OPPOSITION should not trigger PPO
    res1 = classify_plan_name("HIPPO HEALTH GROUP BENEFITS")
    assert res1.label == "Unknown"
    assert res1.in_ppo_network is False
    assert "RULE_EXPLICIT_PPO" not in res1.rule_ids

    res2 = classify_plan_name("OPPOSITION HEALTH PLAN")
    assert res2.label == "Unknown"
    assert res2.in_ppo_network is False
    assert "RULE_EXPLICIT_PPO" not in res2.rule_ids


def test_lowercase_and_punctuation_variants():
    res1 = classify_plan_name("ca l cus ppo-20/500")
    assert res1.label == "PPO"
    assert res1.in_ppo_network is True

    res2 = classify_plan_name("Gold Ppo (500/20)")
    assert res2.label == "PPO"
    assert res2.in_ppo_network is True

    res3 = classify_plan_name("Preferred Provider Organization Bronze Plan")
    assert res3.label == "PPO"
    assert res3.in_ppo_network is True


def test_glued_epo_tokens():
    res1 = classify_plan_name("CA L CUS EPO$15")
    assert res1.label == "EPO"
    assert res1.in_ppo_network is False
    assert "RULE_EXPLICIT_EPO" in res1.rule_ids

    res2 = classify_plan_name("CA L CUS FWP-EPO$10")
    assert res2.label == "EPO"
    assert res2.in_ppo_network is False
    assert "RULE_EXPLICIT_EPO" in res2.rule_ids
