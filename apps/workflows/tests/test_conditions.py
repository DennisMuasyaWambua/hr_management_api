from django.test import TestCase

from apps.workflows.conditions import ConditionEvaluator, _resolve, OPERATORS


class TestResolve(TestCase):

    def test_top_level_key(self):
        self.assertEqual(_resolve({'foo': 'bar'}, 'foo'), 'bar')

    def test_nested_key(self):
        self.assertEqual(_resolve({'a': {'b': 'c'}}, 'a.b'), 'c')

    def test_missing_key_returns_none(self):
        self.assertIsNone(_resolve({'foo': 'bar'}, 'baz'))

    def test_deeply_missing_returns_none(self):
        self.assertIsNone(_resolve({'a': {'b': 'c'}}, 'a.x.y'))

    def test_non_dict_intermediate_returns_none(self):
        self.assertIsNone(_resolve({'a': 'string'}, 'a.b'))


class TestOperators(TestCase):

    def test_eq_true(self):
        self.assertTrue(OPERATORS['eq']('hello', 'hello'))

    def test_eq_false(self):
        self.assertFalse(OPERATORS['eq']('hello', 'world'))

    def test_neq_true(self):
        self.assertTrue(OPERATORS['neq']('a', 'b'))

    def test_neq_false(self):
        self.assertFalse(OPERATORS['neq']('a', 'a'))

    def test_lt_numeric(self):
        self.assertTrue(OPERATORS['lt']('5', '10'))
        self.assertFalse(OPERATORS['lt']('10', '5'))

    def test_lte_numeric(self):
        self.assertTrue(OPERATORS['lte']('5', '5'))
        self.assertTrue(OPERATORS['lte']('4', '5'))
        self.assertFalse(OPERATORS['lte']('6', '5'))

    def test_gt_numeric(self):
        self.assertTrue(OPERATORS['gt']('10', '5'))
        self.assertFalse(OPERATORS['gt']('5', '10'))

    def test_gte_numeric(self):
        self.assertTrue(OPERATORS['gte']('5', '5'))
        self.assertTrue(OPERATORS['gte']('6', '5'))
        self.assertFalse(OPERATORS['gte']('4', '5'))

    def test_contains_string(self):
        self.assertTrue(OPERATORS['contains']('hello world', 'world'))
        self.assertFalse(OPERATORS['contains']('hello', 'xyz'))

    def test_contains_list(self):
        self.assertTrue(OPERATORS['contains'](['a', 'b'], 'a'))
        self.assertFalse(OPERATORS['contains'](['a', 'b'], 'c'))

    def test_contains_non_sequence_returns_false(self):
        self.assertFalse(OPERATORS['contains'](42, 'x'))

    def test_not_contains_string(self):
        self.assertTrue(OPERATORS['not_contains']('hello', 'xyz'))
        self.assertFalse(OPERATORS['not_contains']('hello', 'ell'))

    def test_in_list(self):
        self.assertTrue(OPERATORS['in']('a', ['a', 'b']))
        self.assertFalse(OPERATORS['in']('c', ['a', 'b']))

    def test_in_non_list_returns_false(self):
        self.assertFalse(OPERATORS['in']('a', 'abc'))

    def test_not_in_list(self):
        self.assertTrue(OPERATORS['not_in']('c', ['a', 'b']))
        self.assertFalse(OPERATORS['not_in']('a', ['a', 'b']))

    def test_is_null_true(self):
        self.assertTrue(OPERATORS['is_null'](None, None))

    def test_is_null_false(self):
        self.assertFalse(OPERATORS['is_null']('value', None))

    def test_is_not_null_true(self):
        self.assertTrue(OPERATORS['is_not_null']('value', None))

    def test_is_not_null_false(self):
        self.assertFalse(OPERATORS['is_not_null'](None, None))

    def test_starts_with(self):
        self.assertTrue(OPERATORS['starts_with']('hello', 'he'))
        self.assertFalse(OPERATORS['starts_with']('hello', 'lo'))

    def test_starts_with_none_returns_false(self):
        self.assertFalse(OPERATORS['starts_with'](None, 'he'))

    def test_ends_with(self):
        self.assertTrue(OPERATORS['ends_with']('hello', 'lo'))
        self.assertFalse(OPERATORS['ends_with']('hello', 'he'))

    def test_ends_with_none_returns_false(self):
        self.assertFalse(OPERATORS['ends_with'](None, 'lo'))


class TestConditionEvaluator(TestCase):

    def test_empty_conditions_always_true(self):
        self.assertTrue(ConditionEvaluator.evaluate([], {}, 'AND'))
        self.assertTrue(ConditionEvaluator.evaluate([], {}, 'OR'))

    def test_single_eq_condition_true(self):
        conditions = [{'field': 'status', 'operator': 'eq', 'value': 'active'}]
        self.assertTrue(ConditionEvaluator.evaluate(conditions, {'status': 'active'}))

    def test_single_eq_condition_false(self):
        conditions = [{'field': 'status', 'operator': 'eq', 'value': 'active'}]
        self.assertFalse(ConditionEvaluator.evaluate(conditions, {'status': 'inactive'}))

    def test_and_logic_all_true(self):
        conditions = [
            {'field': 'a', 'operator': 'eq', 'value': '1'},
            {'field': 'b', 'operator': 'eq', 'value': '2'},
        ]
        self.assertTrue(ConditionEvaluator.evaluate(conditions, {'a': '1', 'b': '2'}, 'AND'))

    def test_and_logic_one_false(self):
        conditions = [
            {'field': 'a', 'operator': 'eq', 'value': '1'},
            {'field': 'b', 'operator': 'eq', 'value': '2'},
        ]
        self.assertFalse(ConditionEvaluator.evaluate(conditions, {'a': '1', 'b': 'X'}, 'AND'))

    def test_or_logic_one_true(self):
        conditions = [
            {'field': 'a', 'operator': 'eq', 'value': '1'},
            {'field': 'b', 'operator': 'eq', 'value': '2'},
        ]
        self.assertTrue(ConditionEvaluator.evaluate(conditions, {'a': '1', 'b': 'X'}, 'OR'))

    def test_or_logic_all_false(self):
        conditions = [
            {'field': 'a', 'operator': 'eq', 'value': '1'},
            {'field': 'b', 'operator': 'eq', 'value': '2'},
        ]
        self.assertFalse(ConditionEvaluator.evaluate(conditions, {'a': 'X', 'b': 'Y'}, 'OR'))

    def test_unknown_operator_evaluates_false(self):
        conditions = [{'field': 'x', 'operator': 'unknown_op', 'value': 'y'}]
        self.assertFalse(ConditionEvaluator.evaluate(conditions, {'x': 'y'}))

    def test_missing_field_evaluates_none_correctly(self):
        conditions = [{'field': 'missing', 'operator': 'is_null', 'value': None}]
        self.assertTrue(ConditionEvaluator.evaluate(conditions, {}))

    def test_gte_with_score(self):
        conditions = [{'field': 'score', 'operator': 'gte', 'value': '80'}]
        self.assertTrue(ConditionEvaluator.evaluate(conditions, {'score': '85'}))
        self.assertFalse(ConditionEvaluator.evaluate(conditions, {'score': '75'}))

    def test_type_error_in_comparison_evaluates_false(self):
        conditions = [{'field': 'val', 'operator': 'lt', 'value': 'not_a_number'}]
        self.assertFalse(ConditionEvaluator.evaluate(conditions, {'val': 'also_not_number'}))
