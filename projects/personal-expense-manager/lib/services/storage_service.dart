import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/expense_transaction.dart';

class StorageService {
  static const _key = 'expense_transactions_v1';
  late SharedPreferences _prefs;

  Future<void> init() async {
    _prefs = await SharedPreferences.getInstance();
  }

  List<ExpenseTransaction> loadTransactions() {
    final raw = _prefs.getStringList(_key) ?? const <String>[];
    return raw
        .map((value) => ExpenseTransaction.fromJson(
              jsonDecode(value) as Map<String, dynamic>,
            ))
        .toList();
  }

  Future<void> saveTransactions(List<ExpenseTransaction> items) =>
      _prefs.setStringList(
        _key,
        items.map((item) => jsonEncode(item.toJson())).toList(),
      );
}
