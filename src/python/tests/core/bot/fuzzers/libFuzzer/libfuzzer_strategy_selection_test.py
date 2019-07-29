# Copyright 2019 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Tests for strategy selection file."""

import unittest

from bot.fuzzers.libFuzzer import strategy_selection
from bot.tasks import fuzz_task
from datastore import data_types
from datastore import ndb
from fuzzing import strategy
from system import environment
from tests.test_libs import helpers as test_helpers
from tests.test_libs import test_utils


class TestRandomStrategySelectionGeneratorPatched(unittest.TestCase):
  """Tests whether program properly generates strategy sets for use by the
  launcher."""

  def setUp(self):
    """Set up method for strategy pool generator tests with patch."""
    test_helpers.patch_environ(self)
    test_helpers.patch(self,
                       ['bot.fuzzers.engine_common.decide_with_probability'])
    self.mock.decide_with_probability.return_value = True

  def test_default_pool_deterministic(self):
    """Deterministically tests the random strategy pool generator."""
    strategy_pool = strategy_selection.generate_default_strategy_pool()

    # Ml rnn and radamsa strategies are mutually exclusive. Because of how we
    # patch, ml rnn will evaluate to false, however this depends on the
    # implementation.
    self.assertTrue(
        strategy_pool.do_strategy(strategy.CORPUS_MUTATION_RADAMSA_STRATEGY))
    self.assertFalse(
        strategy_pool.do_strategy(strategy.CORPUS_MUTATION_ML_RNN_STRATEGY))
    self.assertTrue(strategy_pool.do_strategy(strategy.CORPUS_SUBSET_STRATEGY))
    self.assertTrue(
        strategy_pool.do_strategy(strategy.RANDOM_MAX_LENGTH_STRATEGY))
    self.assertTrue(
        strategy_pool.do_strategy(strategy.RECOMMENDED_DICTIONARY_STRATEGY))
    self.assertTrue(strategy_pool.do_strategy(strategy.VALUE_PROFILE_STRATEGY))
    self.assertTrue(strategy_pool.do_strategy(strategy.FORK_STRATEGY))
    self.assertTrue(strategy_pool.do_strategy(strategy.MUTATOR_PLUGIN_STRATEGY))


class TestStrategySelectionPatchless(unittest.TestCase):
  """Tests to see whether a default strategy pool is properly generated by the
  file."""

  def test_default_pool_generator(self):
    """Ensures that a call to generate_default_strategy_pool does not yield an
    exception. Deterministic behaviors are tested in the previous test."""
    strategy_selection.generate_default_strategy_pool()


@test_utils.with_cloud_emulators('datastore')
class TestMultiArmedBanditStrategySelectionPatch(unittest.TestCase):
  """Tests whether a multi armed bandit strategy pool is properly
  generated according to the specified distribution."""

  def setUp(self):
    """Put data in the local ndb table the tests to query from and set
    bandit selection environment variable."""
    test_helpers.patch_environ(self)

    data = []

    strategy1 = data_types.FuzzStrategyProbability()
    strategy1.strategy_name = 'fork,corpus_subset,recommended_dict,'
    strategy1.probability_medium_temperature = 0.33
    strategy1.probability_high_temperature = 0.33
    strategy1.probability_low_temperature = 0.33
    data.append(strategy1)

    strategy2 = data_types.FuzzStrategyProbability()
    strategy2.strategy_name = ('random_max_len,corpus_mutations_ml_rnn,'
                               'value_profile,recommended_dict,')
    strategy2.probability_medium_temperature = 0.34
    strategy2.probability_high_temperature = 0.34
    strategy2.probability_low_temperature = 0.34
    data.append(strategy2)

    strategy3 = data_types.FuzzStrategyProbability()
    strategy3.strategy_name = ('corpus_mutations_radamsa,'
                               'random_max_len,corpus_subset,')
    strategy3.probability_medium_temperature = 0.33
    strategy3.probability_high_temperature = 0.33
    strategy3.probability_low_temperature = 0.33
    data.append(strategy3)
    ndb.put_multi(data)

    distribution = fuzz_task.get_strategy_distribution_from_ndb()

    environment.set_value('USE_BANDIT_STRATEGY_SELECTION', True)
    environment.set_value('STRATEGY_SELECTION_DISTRIBUTION', distribution)

  def test_multi_armed_bandit_strategy_pool(self):
    """Ensures a call to the multi armed bandit strategy selection function
    doesn't yield an exception through any of the experimental paths."""
    environment.set_value('STRATEGY_SELECTION_METHOD', 'default')
    strategy_selection.generate_weighted_strategy_pool()
    environment.set_value('STRATEGY_SELECTION_METHOD',
                          'multi_armed_bandit_medium')
    strategy_selection.generate_weighted_strategy_pool()
    environment.set_value('STRATEGY_SELECTION_METHOD',
                          'multi_armed_bandit_high')
    strategy_selection.generate_weighted_strategy_pool()
    environment.set_value('STRATEGY_SELECTION_METHOD', 'multi_armed_bandit_low')
    strategy_selection.generate_weighted_strategy_pool()


@test_utils.with_cloud_emulators('datastore')
class TestMultiArmedBanditStrategySelection(unittest.TestCase):
  """Tests whether multi armed bandit strategy pool is properly generated
  according to the specified distribution.

  Deterministic tests. Only one strategy is put in the ndb table upon setup,
  so we know what the drawn strategy pool should be."""

  def setUp(self):
    """Put data in the local ndb table the tests to query from."""
    test_helpers.patch_environ(self)
    test_helpers.patch(self,
                       ['bot.fuzzers.engine_common.decide_with_probability'])
    self.mock.decide_with_probability.return_value = True

    data = []

    strategy1 = data_types.FuzzStrategyProbability()
    strategy1.strategy_name = ('random_max_len,corpus_mutations_ml_rnn,'
                               'value_profile,recommended_dict,')
    strategy1.probability_medium_temperature = 1
    strategy1.probability_high_temperature = 1
    strategy1.probability_low_temperature = 1
    data.append(strategy1)
    ndb.put_multi(data)

    distribution = fuzz_task.get_strategy_distribution_from_ndb()

    environment.set_value('USE_BANDIT_STRATEGY_SELECTION', True)
    environment.set_value('STRATEGY_SELECTION_DISTRIBUTION', distribution)

  def test_strategy_pool_medium_temperature(self):
    """Tests whether a proper strategy pool is returned by the multi armed
    bandit selection implementation with medium temperature.

    Based on deterministic strategy selection. Mutator plugin is patched to
    be included in our strategy pool."""
    environment.set_value('STRATEGY_SELECTION_METHOD',
                          'multi_armed_bandit_medium')
    strategy_pool = strategy_selection.generate_weighted_strategy_pool()
    self.assertTrue(
        strategy_pool.do_strategy(strategy.CORPUS_MUTATION_ML_RNN_STRATEGY))
    self.assertTrue(
        strategy_pool.do_strategy(strategy.RANDOM_MAX_LENGTH_STRATEGY))
    self.assertTrue(strategy_pool.do_strategy(strategy.VALUE_PROFILE_STRATEGY))
    self.assertTrue(
        strategy_pool.do_strategy(strategy.RECOMMENDED_DICTIONARY_STRATEGY))
    self.assertFalse(
        strategy_pool.do_strategy(strategy.CORPUS_MUTATION_RADAMSA_STRATEGY))
    self.assertFalse(strategy_pool.do_strategy(strategy.CORPUS_SUBSET_STRATEGY))
    self.assertFalse(strategy_pool.do_strategy(strategy.FORK_STRATEGY))
    self.assertTrue(strategy_pool.do_strategy(strategy.MUTATOR_PLUGIN_STRATEGY))

  def test_strategy_pool_high_temperature(self):
    """Tests whether a proper strategy pool is returned by the multi armed
    bandit selection implementation with high temperature.

    Based on deterministic strategy selection. Mutator plugin is patched to
    be included in our strategy pool."""
    environment.set_value('STRATEGY_SELECTION_METHOD',
                          'multi_armed_bandit_high')
    strategy_pool = strategy_selection.generate_weighted_strategy_pool()
    self.assertTrue(
        strategy_pool.do_strategy(strategy.CORPUS_MUTATION_ML_RNN_STRATEGY))
    self.assertTrue(
        strategy_pool.do_strategy(strategy.RANDOM_MAX_LENGTH_STRATEGY))
    self.assertTrue(strategy_pool.do_strategy(strategy.VALUE_PROFILE_STRATEGY))
    self.assertTrue(
        strategy_pool.do_strategy(strategy.RECOMMENDED_DICTIONARY_STRATEGY))
    self.assertFalse(
        strategy_pool.do_strategy(strategy.CORPUS_MUTATION_RADAMSA_STRATEGY))
    self.assertFalse(strategy_pool.do_strategy(strategy.CORPUS_SUBSET_STRATEGY))
    self.assertFalse(strategy_pool.do_strategy(strategy.FORK_STRATEGY))
    self.assertTrue(strategy_pool.do_strategy(strategy.MUTATOR_PLUGIN_STRATEGY))

  def test_strategy_pool_low_temperature(self):
    """Tests whether a proper strategy pool is returned by the multi armed
    bandit selection implementation with low temperature.

    Based on deterministic strategy selection. Mutator plugin is patched to
    be included in our strategy pool."""
    environment.set_value('STRATEGY_SELECTION_METHOD', 'multi_armed_bandit_low')
    strategy_pool = strategy_selection.generate_weighted_strategy_pool()
    self.assertTrue(
        strategy_pool.do_strategy(strategy.CORPUS_MUTATION_ML_RNN_STRATEGY))
    self.assertTrue(
        strategy_pool.do_strategy(strategy.RANDOM_MAX_LENGTH_STRATEGY))
    self.assertTrue(strategy_pool.do_strategy(strategy.VALUE_PROFILE_STRATEGY))
    self.assertTrue(
        strategy_pool.do_strategy(strategy.RECOMMENDED_DICTIONARY_STRATEGY))
    self.assertFalse(
        strategy_pool.do_strategy(strategy.CORPUS_MUTATION_RADAMSA_STRATEGY))
    self.assertFalse(strategy_pool.do_strategy(strategy.CORPUS_SUBSET_STRATEGY))
    self.assertFalse(strategy_pool.do_strategy(strategy.FORK_STRATEGY))
    self.assertTrue(strategy_pool.do_strategy(strategy.MUTATOR_PLUGIN_STRATEGY))
