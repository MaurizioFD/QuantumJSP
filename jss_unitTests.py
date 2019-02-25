# Copyright 2019 D-Wave Systems Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from itertools import product
from re import match
import unittest

from dimod import ExactSolver
from jobShopScheduler import JobShopScheduler
from tabu import TabuSampler


def fill_with_zeros(expected_solution_dict, job_dict, max_time):
    """Fills the 'missing' expected_solution_dict keys with a value of 0.
    args:
        expected_solution_dict: a dictionary.  {taskName: taskValue, ..}
        job_dict: a dictionary. {jobName: [(machineVal, taskTimeSpan), ..], ..}
        max_time: integer. Max time for the schedule
    """
    for job, tasks in job_dict.items():
        for pos in range(len(tasks)):
            prefix = str(job) + "_" + str(pos)

            for t in range(max_time):
                key = prefix + "," + str(t)

                if key not in expected_solution_dict:
                    expected_solution_dict[key] = 0


def get_energy(solution_dict, bqm):
    min_energy = float('inf')
    aux_variables = [v for v in bqm.variables if match("aux\d+$", v)]
    print("Number of auxiliary variables: ", len(aux_variables))

    # Try all possible values of auxiliary variables
    for aux_values in product([0, 1], repeat=len(aux_variables)):
        for variable, value in zip(aux_variables, aux_values):
            solution_dict[variable] = value

        temp_energy = bqm.energy(solution_dict)

        if temp_energy < min_energy:
            min_energy = temp_energy

    return min_energy


class TestIndividualJSSConstraints(unittest.TestCase):
    def test_oneStartConstraint(self):
        jobs = {"car": [("key", 2), ("gas", 1)],
                "stove": [("gas", 4)]}
        jss = JobShopScheduler(jobs, 3)
        jss._add_one_start_constraint()

        # Tasks only start once
        one_start_solution = {"car_0,0": 1, "car_0,1": 0, "car_0,2": 0,
                              "car_1,0": 0, "car_1,1": 1, "car_1,2": 0,
                              "stove_0,0": 1, "stove_0,1": 0, "stove_0,2": 0}

        # Task car_1 starts twice; it starts on times 0 and 1
        multi_start_solution = {"car_0,0": 1, "car_0,1": 0, "car_0,2": 0,
                                "car_1,0": 0, "car_1,1": 1, "car_1,2": 0,
                                "stove_0,0": 1, "stove_0,1": 1, "stove_0,2": 0}

        self.assertTrue(jss.csp.check(one_start_solution))
        self.assertFalse(jss.csp.check(multi_start_solution))

    def test_precedenceConstraint(self):
        jobs = {0: [("m1", 2), ("m2", 1)]}
        max_time = 4
        jss = JobShopScheduler(jobs, max_time)
        jss._add_precedence_constraint()

        # Task 0_0 starts after task 0_1
        backward_solution = {"0_0,3": 1, "0_1,0": 1}
        fill_with_zeros(backward_solution, jobs, max_time)

        # Tasks start at the same time
        same_start_solution = {"0_0,1": 1, "0_1,1": 1}
        fill_with_zeros(same_start_solution, jobs, max_time)

        # Task 0_1 starts before 0_0 has completed
        overlap_solution = {"0_0,1": 1, "0_1,2": 1}
        fill_with_zeros(overlap_solution, jobs, max_time)

        # Tasks follows correct order and respects task duration
        ordered_solution = {"0_0,0": 1, "0_1,2": 1}
        fill_with_zeros(ordered_solution, jobs, max_time)

        self.assertFalse(jss.csp.check(backward_solution))
        self.assertFalse(jss.csp.check(same_start_solution))
        self.assertFalse(jss.csp.check(overlap_solution))
        self.assertTrue(jss.csp.check(ordered_solution))

    def test_shareMachineConstraint(self):
        jobs = {"movie": [("pay", 1), ("watch", 3)],
                "tv": [("watch", 1)],
                "netflix": [("watch", 3)]}
        max_time = 7
        jss = JobShopScheduler(jobs, max_time)
        jss._add_share_machine_constraint()

        # All jobs 'watch' at the same time
        same_start_solution = {"movie_0,0": 1, "movie_1,1": 1,
                               "tv_0,1": 1,
                               "netflix_0,1": 1}
        fill_with_zeros(same_start_solution, jobs, max_time)

        # 'movie' does not obey precedence, but respects machine sharing
        bad_order_share_solution = {"movie_0,4": 1, "movie_1,0": 1,
                                    "tv_0,3": 1,
                                    "netflix_0,4": 1}
        fill_with_zeros(bad_order_share_solution, jobs, max_time)

        self.assertFalse(jss.csp.check(same_start_solution))
        self.assertTrue(jss.csp.check(bad_order_share_solution))

    def test_absurdTimesAreRemoved(self):
        pass


class TestCombinedJSSConstraints(unittest.TestCase):
    # TODO: test job with no tasks
    # TODO: test no jobs
    # TODO: test non-integer durations
    # TODO: insufficient max_time
    def test_denseSchedule(self):
        jobs = {"a": [(1, 2), (2, 2), (3, 2)],
                "b": [(3, 3), (2, 1), (1, 1)],
                "c": [(2, 2), (1, 3), (2, 1)]}
        max_time = 6
        jss = JobShopScheduler(jobs, max_time)
        jss.get_bqm()   # Run job shop scheduling constraints

        # Solution that obeys all constraints
        good_solution = {"a_0,0": 1, "a_1,2": 1, "a_2,4": 1,
                         "b_0,0": 1, "b_1,4": 1, "b_2,5": 1,
                         "c_0,0": 1, "c_1,2": 1, "c_2,5": 1}
        fill_with_zeros(good_solution, jobs, max_time)

        # Tasks a_1 and b_1 overlap in time on machine 2
        overlap_solution = {"a_0,0": 1, "a_1,2": 1, "a_2,4": 1,
                            "b_0,0": 1, "b_1,3": 1, "b_2,5": 1,
                            "c_0,0": 1, "c_1,2": 1, "c_2,5": 1}
        fill_with_zeros(overlap_solution, jobs, max_time)

        self.assertTrue(jss.csp.check(good_solution))
        self.assertFalse(jss.csp.check(overlap_solution))

    def test_relaxedSchedule(self):
        jobs = {"breakfast": [("cook", 2), ("eat", 1)],
                "music": [("play", 2)]}
        max_time = 7
        jss = JobShopScheduler(jobs, max_time)
        jss.get_bqm()   # Run job shop scheduling constraints

        # Solution obeys all constraints
        good_solution = {"breakfast_0,0": 1, "breakfast_1,4": 1,
                         "music_0,3": 1}
        fill_with_zeros(good_solution, jobs, max_time)

        # 'breakfast' tasks are out of order
        bad_order_solution = {"breakfast_0,1": 1, "breakfast_1,0": 1,
                              "music_0,0": 1}
        fill_with_zeros(bad_order_solution, jobs, max_time)

        self.assertTrue(jss.csp.check(good_solution))
        self.assertFalse(jss.csp.check(bad_order_solution))


class TestJSSExactSolverResponse(unittest.TestCase):
    def compare(self, response, expected):
        """Comparing response to expected results
        """
        # Comparing variables found in sample and expected
        expected_keys = set(expected.keys())
        sample_keys = set(response.keys())
        common_keys = expected_keys & sample_keys   # TODO: NO AUX
        different_keys = sample_keys - expected_keys  # sample_keys is a superset

        # Check that common variables match
        for key in common_keys:
            if match('aux\d+$', key):
                continue

            self.assertEqual(response[key], expected[key], "Failed on key {}".format(key))

        # Check that non-existent 'sample' variables are 0
        for key in different_keys:
            if match('aux\d+$', key):
                continue

            self.assertEqual(response[key], 0, "Failed on key {}".format(key))

    def test_tinySchedule(self):
        jobs = {"a": [(1, 1), (2, 1)],
                "b": [(2, 1)]}
        max_time = 2

        # Get exact sample from Job Shop Scheduler BQM
        jss = JobShopScheduler(jobs, max_time)
        bqm = jss.get_bqm()
        response = ExactSolver().sample(bqm)
        response_sample = next(response.samples())

        # Verify that response_sample obeys constraints
        self.assertTrue(jss.csp.check(response_sample))

        # Create expected solution
        expected = {"a_0,0": 1, "a_1,1": 1, "b_0,0": 1}

        # Compare variable values
        self.compare(response_sample, expected)

    def test_largerSchedule(self):
        jobs = {'small1': [(1, 1)],
                'small2': [(2, 2)],
                'longJob': [(0, 1), (1, 1), (2, 1)]}
        max_time = 4

        # Get exact sample from Job Shop Scheduler BQM
        jss = JobShopScheduler(jobs, max_time)
        bqm = jss.get_bqm()
        response = ExactSolver().sample(bqm)
        response_sample = next(response.samples())

        # Verify that response_sample obeys constraints
        self.assertTrue(jss.csp.check(response_sample))

        # Create expected solution
        expected = {"small1_0,0": 1,
                    "small2_0,0": 1,
                    "longJob_0,0": 1, "longJob_1,1": 1, "longJob_2,2": 1}

        # Compare variable values
        self.compare(response_sample, expected)


class TestJSSHeuristicResponse(unittest.TestCase):
    #TODO: make a general compare function
    def compare(self, response, expected):
        """Comparing response to expected results
        """
        # Comparing variables found in sample and expected
        expected_keys = set(expected.keys())
        sample_keys = set(response.keys())
        common_keys = expected_keys & sample_keys   # TODO: NO AUX
        different_keys = sample_keys - expected_keys  # sample_keys is a superset

        # Check that common variables match
        for key in common_keys:
            if match('aux\d+$', key):
                continue

            self.assertEqual(response[key], expected[key], "Failed on key {}".format(key))

        # Check that non-existent 'sample' variables are 0
        for key in different_keys:
            if match('aux\d+$', key):
                continue

            self.assertEqual(response[key], 0, "Failed on key {}".format(key))

    def test_dense_schedule(self):
        # jobs = {'small1': [(1, 1), (0, 2)],
        #         'small2': [(2, 2), (0, 1)],
        #         'longJob': [(0, 1), (1, 1), (2, 1)]}
        # max_time = 4
        jobs = {"j0": [(1, 2), (2, 2), (3, 2)],
                "j1": [(3, 4), (2, 1), (1, 1)],
                "j2": [(2, 2), (1, 3), (2, 1)]}
        max_time = 7

        # Get JSS BQM
        scheduler = JobShopScheduler(jobs, max_time)
        bqm = scheduler.get_bqm()
        print("Number of bqm variables: ", len(bqm.variables))

        # Expected solution
        expected = {"j0_0,0": 1, "j0_1,2": 1, "j0_2,4": 1,
                    "j1_0,0": 1, "j1_1,4": 1, "j1_2,5": 1,
                    "j2_0,0": 1, "j2_1,2": 1, "j2_2,5": 1}
        fill_with_zeros(expected, jobs, max_time)
        expected_energy = get_energy(expected, bqm)
        print("Expected Energy: ", expected_energy)

        # Sampled solution
        # response = EmbeddingComposite(DWaveSampler()).sample(bqm, num_reads=10000)
        # response_sample, sample_energy, _, _ = next(response.data())
        # response = SimulatedAnnealingSampler().sample(bqm, num_reads=2000, beta_range=[0.01, 10])
        response = TabuSampler().sample(bqm, num_reads=2000)
        response_sample, sample_energy, _ = next(response.data())
        print("Sample Energy: ", sample_energy)
        print("Dense sample schedule: ", response_sample)

        # Check response sample
        self.assertTrue(scheduler.csp.check(response_sample))
        self.assertEqual(expected_energy, sample_energy)
        self.compare(response_sample, expected)

    def test_simple_schedule_more_machines(self):
        jobs = {"j0": [(0, 1), (3, 1)],
                "j1": [(1, 1)],
                "j2": [(2, 1)],
                "j3": [(3, 1)],
                "j4": [(4, 1)]}
        max_time = 3

        # Get JSS BQM
        scheduler = JobShopScheduler(jobs, max_time)
        bqm = scheduler.get_bqm()
        print("Number of bqm variables: ", len(bqm.variables))

        # Expected solution
        expected = {"j0_0,0": 1, "j0_1,1": 1,
                    "j1_0,0": 1,
                    "j2_0,0": 1,
                    "j3_0,0": 1,
                    "j4_0,0": 1}
        fill_with_zeros(expected, jobs, max_time)
        expected_energy = get_energy(expected, bqm)
        print("Expected Energy: ", expected_energy)

        # Sampled solution
        # response = EmbeddingComposite(DWaveSampler()).sample(bqm, num_reads=10000)
        # response_sample, sample_energy, _, chain_break_fraction = next(response.data())
        # print("Chain Break Fraction: ", chain_break_fraction)
        # response = SimulatedAnnealingSampler().sample(bqm, num_reads=2000, beta_range=[0.01, 10])
        response = TabuSampler().sample(bqm, num_reads=2000)
        response_sample, sample_energy, _ = next(response.data())
        print("Sample Energy: ", sample_energy)
        print("Simple sample schedule: ", response_sample)

        # Print response
        self.assertTrue(scheduler.csp.check(response_sample))
        self.assertEqual(expected_energy, sample_energy)
        self.compare(response_sample, expected)

    def test_multiple_optimal_solutions(self):
        jobs = {"car": [("gas", 1), ("road", 2), ("park", 1)],
                "flat_tire": [("park", 1)]}
        # max_time = 7
        max_time = 5

        # Get JSS BQM
        scheduler = JobShopScheduler(jobs, max_time)
        bqm = scheduler.get_bqm()

        # A possible optimal solution
        possible_optimal = {"car_0,0": 1, "car_1,1": 1, "car_2,3": 1,
                            "flat_tire_0,0": 1}
        fill_with_zeros(possible_optimal, jobs, max_time)
        optimal_energy = get_energy(possible_optimal, bqm)

        # Sampled solution
        response = TabuSampler().sample(bqm, num_reads=2000)
        response_sample, sample_energy, _ = next(response.data())

        # Verify constraints and energy
        self.assertTrue(scheduler.csp.check(response_sample))
        self.assertEqual(optimal_energy, sample_energy)

        # Verify sampled solution's makespan by checking all final tasks
        optimal_makespan = 4
        bad_events = ["car_2," + str(i) for i in range(optimal_makespan, max_time)]
        bad_events += ["flat_tire_0," + str(i) for i in range(optimal_makespan, max_time)]

        for bad_event in bad_events:
            try:
                self.assertEqual(response_sample[bad_event], 0, "Bad event {} is not 0".format(bad_event))
            except KeyError:
                # If key does not exist, event is automatically false
                pass


if __name__ == "__main__":
    unittest.main()