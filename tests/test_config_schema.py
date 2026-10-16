"""Documented stdlib subset; optional differential checks are explicit only."""
import copy
import os
import unittest

import support

config = support.helper('config')


class SchemaTests(unittest.TestCase):
    def test_optional_bot_authors_closed_schema_and_legacy_compatibility(self):
        schema = config.load(support.REPO/'schemas/config.schema.json')
        data = config.load(support.REPO/'examples/config/config.yaml')
        config.validate_schema(data,schema)
        data['review_bots'] = {'copilot':{'enabled':True,'required':False,'config':'.github/copilot-instructions.md','authors':['Copilot','custom-review[bot]']}}
        config.validate_schema(data,schema)
        for authors in (['same','same'],['bad login'],['$(command)'],[True],['a'*129]):
            with self.subTest(authors=authors),self.assertRaises(config.ConfigError):
                invalid = copy.deepcopy(data)
                invalid['review_bots']['copilot']['authors'] = authors
                config.validate_schema(invalid,schema)
        data['review_bots']['copilot']['unknown'] = True
        with self.assertRaises(config.ConfigError):
            config.validate_schema(data,schema)

    def test_optional_autonomy_and_planning_modes_preserve_legacy_and_reject_unknowns(self):
        schema = config.load(support.REPO/'schemas/config.schema.json')
        data = config.load(support.REPO/'examples/config/config.yaml')
        config.validate_schema(data, schema)
        for mode in ('supervised', 'risk-adaptive'):
            for method in ('bmad', 'native'):
                data['autonomy']['mode'] = mode
                data['planning']['method'] = method
                config.validate_schema(data, schema)
        for section, key in (('autonomy', 'mode'), ('planning', 'method')):
            original = data[section][key]
            for value in (True, None, 'unrestricted', '*'):
                data[section][key] = value
                with self.assertRaises(config.ConfigError):
                    config.validate_schema(data, schema)
            data[section][key] = original

    def test_supported_keywords(self):
        schema = {'type':'object','required':['x'],'properties':{'x':{'$ref':'#/$defs/n'}},'additionalProperties':False,'$defs':{'n':{'type':'integer','minimum':1,'maximum':4}}}
        config.validate_schema({'x':2},schema)
        for data in ({},{'x':True},{'x':0},{'x':5},{'x':2,'extra':0}):
            with self.subTest(data=data), self.assertRaises(config.ConfigError):
                config.validate_schema(data,schema)

    def test_oneof_exactly_one_and_patterns_all_apply(self):
        with self.assertRaises(config.ConfigError):
            config.validate_schema(1,{'oneOf':[{'type':'number'},{'type':'integer'}]})
        with self.assertRaises(config.ConfigError):
            config.validate_schema({'abc':3},{'patternProperties':{'^a':{'minimum':4},'c$':{'type':'integer'}},'additionalProperties':False})
        config.validate_schema(['abc'],{'type':'array','minItems':1,'maxItems':2,'uniqueItems':True,'items':{'type':'string','minLength':2,'maxLength':4,'pattern':'^a'}})
        with self.assertRaises(config.ConfigError):
            config.validate_schema([True,True],{'uniqueItems':True})
        config.validate_schema([True,1],{'uniqueItems':True})

    def test_numeric_equality_is_recursive_and_booleans_stay_distinct(self):
        config.validate_schema([1.0], {'const':[1]})
        config.validate_schema({'x':1.0}, {'enum':[{'x':1}]})
        for value in ([1,1.0], [{'x':[1]},{'x':[1.0]}]):
            with self.assertRaises(config.ConfigError):
                config.validate_schema(value, {'uniqueItems':True})
        config.validate_schema([{'x':True},{'x':1}], {'uniqueItems':True})
        with self.assertRaises(config.ConfigError):
            config.validate_schema({'x':True}, {'const':{'x':1}})

    def test_unused_unsupported_reference_cycles_remote_and_bounds(self):
        for schema in ({'$defs':{'unused':{'format':'email'}}}, {'$ref':'https://example.test/schema'}, {'$defs':{'a':{'$ref':'#/$defs/a'}}}, {'$ref':'#/$defs/missing'}):
            with self.subTest(schema=schema), self.assertRaises(config.ConfigError):
                config.validate_schema({},schema)
        data = {}
        for _ in range(34):
            data = {'x':data}
        with self.assertRaises(config.ConfigError):
            config.bounded(data)

    @unittest.skipUnless(os.environ.get('SF_CONFIG_JSONSCHEMA_CROSSCHECK') == '1', 'optional jsonschema cross-check not requested')
    def test_optional_jsonschema_crosscheck(self):
        try:
            import importlib
            jsonschema = importlib.import_module('jsonschema')
        except ImportError:
            self.skipTest('optional jsonschema package unavailable')
        schema = config.load(support.REPO/'schemas/config.schema.json')
        jsonschema.Draft202012Validator.check_schema(schema)
        for path in (support.REPO/'tests/fixtures/config').glob('*.yaml'):
            try:
                data = config.load(path)
            except config.ConfigError:
                continue
            try:
                config.validate_schema(copy.deepcopy(data), schema)
                actual = True
            except config.ConfigError:
                actual = False
            expected = not list(jsonschema.Draft202012Validator(schema).iter_errors(data))
            self.assertEqual(expected,actual,path.name)
