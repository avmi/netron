''' TorchScript metadata script '''

import collections
import json
import os
import re
import sys

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_dir)
sys.pycache_prefix = os.path.join(root_dir, 'dist', 'pycache', 'test', 'backend')
pytorch = __import__('source.pytorch').pytorch

source_dir = os.path.join(root_dir, 'source')
third_party_dir = os.path.join(root_dir, 'third_party')
metadata_file = os.path.join(source_dir, 'pytorch-metadata.json')
pytorch_source_dir = os.path.join(third_party_dir, 'source', 'pytorch')

def _read(path):
    with open(path, 'r', encoding='utf-8') as file:
        return file.read()

def _write(path, content):
    with open(path, 'w', encoding='utf-8') as file:
        file.write(content)

def _read_metadata():
    metadata = {}
    for value in json.loads(_read(metadata_file)):
        key = value['name']
        if key in metadata:
            raise ValueError(f"Duplicate key '{key}'")
        metadata[key] = value
    return metadata

def _write_metadata(value):
    metadata = list(collections.OrderedDict(sorted(value.items())).values())
    content = json.dumps(metadata, indent=2, ensure_ascii=False)
    content = re.sub(r'\s {8}', ' ', content)
    content = re.sub(r',\s {8}', ', ', content)
    content = re.sub(r'\s {6}}', ' }', content)
    _write(metadata_file, content)

schema_source_files = [
    ('aten/src/ATen/native/native_functions.yaml',
        re.compile(r'-\s*func:\s*(.*)', re.MULTILINE), 'aten::'),
    ('aten/src/ATen/native/quantized/library.cpp',
        re.compile(r'TORCH_SELECTIVE_SCHEMA\("(.*)"\)', re.MULTILINE)),
    ('aten/src/ATen/native/xnnpack/RegisterOpContextClass.cpp',
        re.compile(r'TORCH_SELECTIVE_SCHEMA\("(.*)"', re.MULTILINE)),
    ('torch/csrc/jit/runtime/register_prim_ops.cpp',
        re.compile(r'(aten::.*->\s*.*)"', re.MULTILINE)),
    ('torch/csrc/jit/runtime/register_prim_ops.cpp',
        re.compile(r'(prim::.*->\s*.*)"', re.MULTILINE)),
    ('torch/csrc/jit/runtime/register_prim_ops_fulljit.cpp',
        re.compile(r'(aten::.*->\s*.*)"', re.MULTILINE)),
    ('torch/csrc/jit/runtime/register_special_ops.cpp',
        re.compile(r'(aten::.*->\s*.*)"', re.MULTILINE)),
    ('aten/src/ATen/native/RNN.cpp',
        re.compile(r'TORCH_SELECTIVE_SCHEMA\("(.*)"', re.MULTILINE)),
    ('torch/jit/_shape_functions.py',
        re.compile(r'(prim::.*->\s*.*)"', re.MULTILINE))
]

known_schema_definitions = [
    'aten::as_tensor(Tensor(a) data, *, ScalarType? dtype=None, Device? device=None) -> Tensor(b|a)', # pylint: disable=line-too-long
    'aten::as_tensor.bool(bool t, *, ScalarType? dtype=None, Device? device=None) -> Tensor',
    'aten::as_tensor.complex(complex t, *, ScalarType? dtype=None, Device? device=None) -> Tensor',
    'aten::as_tensor.float(float t, *, ScalarType? dtype=None, Device? device=None) -> Tensor',
    'aten::as_tensor.int(int t, *, ScalarType? dtype=None, Device? device=None) -> Tensor',
    'aten::as_tensor.list(t[] data, *, ScalarType? dtype=None, Device? device=None) -> Tensor'
]

def _parse_schemas():
    schemas = {}
    definitions = set()
    for entry in schema_source_files:
        path = os.path.join(pytorch_source_dir, entry[0])
        content = _read(path)
        content = content.splitlines()
        content = filter(lambda _: not _.startswith('#'), content)
        content = '\n'.join(content)
        for value in entry[1].findall(content):
            value = re.sub(r'\n|\r|\s*"', '', value) if value.startswith('_caffe2::') else value
            definition = entry[2] + value if len(entry) > 2 else value
            if not definition in definitions:
                definitions.add(definition)
                schema = pytorch.Schema(definition)
                if schema.name in schemas:
                    raise KeyError(schema.name)
                schemas[schema.name] = schema
    for definition in known_schema_definitions:
        schema = pytorch.Schema(definition)
        schemas[schema.name] = schema
    return schemas

def _filter_schemas(schemas, types):

    keys = set(map(lambda _: _.split('.')[0], types.keys()))
    filtered_schemas = set()
    for schema in schemas.values():
        for key in keys:
            if schema.name == key or schema.name.startswith(key + '.'):
                filtered_schemas.add(schema.name)
    for schema in schemas.values():
        if schema.name.startswith('aten::pop'):
            filtered_schemas.add(schema.name)
    # filtered_schemas = set(types.keys())
    # content = _read('list.csv')
    # regex = re.compile(r'Unsupported function \'(.*)\' in', re.MULTILINE)
    # matches = set()
    # for match in regex.findall(content):
    #     if match.startswith('torch.'):
    #         matches.add('aten::' + match[6:])
    #     if match.startswith('ops.') and len(match.split('.')) > 2:
    #         matches.add(match[4:].replace('.', '::'))
    # for schema in schemas.values():
    #     for match in matches:
    #         if schema.name.startswith(match):
    #             filtered_schemas.add(schema.name)
    return dict(filter(lambda _: _[0] in filtered_schemas, schemas.items()))

def _check_schemas(schemas): # pylint: disable=unused-argument
    # import torch
    # for name in dir(torch.ops.aten):
    #     if name.startswith('__') or name == 'name':
    #         continue
    #     packet = getattr(torch.ops.aten, name)
    #     for overload in packet.overloads():
    #         key = 'aten::' + name + ('.' + overload if overload != 'default' else '')
    #         overload_schema = str(getattr(packet, overload)._schema)
    #         if key in schemas:
    #             schema = schemas[key]
    #             if overload_schema != str(schema):
    #                 print(overload_schema)
    #                 print(schema)
    pass

def _check_types(types, schemas):
    types = dict(types.items())
    for schema in schemas.values():
        if schema.name in types:
            types.pop(schema.name)
    for key in list(types.keys()):
        if key.startswith('torch.nn') or key.startswith('__torch__.'):
            types.pop(key)
        if key.startswith('torchvision::') or \
           key.startswith('torchaudio::') or \
           key.startswith('neuron::'):
            types.pop(key)
        if key.startswith('_caffe2::'):
            types.pop(key)
    types.pop('aten::fft')
    types.pop('aten::mul.ScalarT')
    types.pop('aten::classes._nnapi.Compilation')
    types.pop('aten::arange.start_out_')
    types.pop('aten::_native_batch_norm_legit_functional')
    types.pop('aten::gt.float')
    types.pop('aten::gt.float_int')
    types.pop('aten::gt.int')
    types.pop('aten::gt.int_float')
    types.pop('aten::add.int')
    types.pop('aten::add.float')
    types.pop('aten::add.str')
    types.pop('aten::le.float')
    types.pop('aten::le.float_int')
    types.pop('aten::le.int')
    types.pop('aten::le.int_float')
    types.pop('aten::remainder.int')
    types.pop('aten::remainder.float32')
    types.pop('aten::sub.int')
    types.pop('aten::sub.float')
    types.pop('aten::sub.str')
    if len(types) > 0:
        raise Exception('\n'.join(list(types.keys()))) # pylint: disable=broad-exception-raised

def _metadata():
    types = _read_metadata()
    schemas = _parse_schemas()
    _check_types(types, schemas)
    _check_schemas(schemas)
    filtered_schemas = _filter_schemas(schemas, types)
    metadata = pytorch.Metadata(types)
    for schema in filtered_schemas.values():
        metadata.type(schema)
    _write_metadata(types)

def main(): # pylint: disable=missing-function-docstring
    _metadata()

if __name__ == '__main__':
    main()
