import 'dart:convert';
import 'dart:io';

/// Uma resposta REAL da API da Jetson, gravada por `scripts/export_api_fixtures.py`.
/// Os testes do app leem estes arquivos: se o contrato mudar, eles são regravados e o que o
/// app não entender aparece aqui.
dynamic fixture(String name) => jsonDecode(File('test/fixtures/$name.json').readAsStringSync());

Map<String, dynamic> fixtureMap(String name) => (fixture(name) as Map).cast<String, dynamic>();
