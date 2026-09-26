import 'package:flutter/foundation.dart';
import '../models/expense_transaction.dart';
import '../services/storage_service.dart';

class ExpenseController extends ChangeNotifier {
  ExpenseController(this.storage) {
    _items = storage.loadTransactions();
    _sort();
  }

  final StorageService storage;
  List<ExpenseTransaction> _items = [];
  String _query = '';
  TransactionType? _filter;

  static const categories = <String>[
    'Food', 'Transport', 'Shopping', 'Bills', 'Health', 'Salary', 'Other'
  ];

  List<ExpenseTransaction> get all => List.unmodifiable(_items);
  TransactionType? get filter => _filter;

  List<ExpenseTransaction> get visible {
    final q = _query.trim().toLowerCase();
    return _items.where((item) {
      final typeOk = _filter == null || item.type == _filter;
      final textOk = q.isEmpty ||
          item.category.toLowerCase().contains(q) ||
          item.note.toLowerCase().contains(q);
      return typeOk && textOk;
    }).toList();
  }

  double get income => _sum(TransactionType.income);
  double get expenses => _sum(TransactionType.expense);
  double get balance => income - expenses;

  double _sum(TransactionType type) => _items
      .where((item) => item.type == type)
      .fold(0, (sum, item) => sum + item.amount);

  void setQuery(String value) {
    _query = value;
    notifyListeners();
  }

  void setFilter(TransactionType? value) {
    _filter = value;
    notifyListeners();
  }

  Future<void> add({
    required double amount,
    required TransactionType type,
    required String category,
    required DateTime date,
    String note = '',
  }) async {
    _validate(amount, category);
    _items.add(ExpenseTransaction(
      id: DateTime.now().microsecondsSinceEpoch.toString(),
      amount: amount,
      type: type,
      category: category,
      date: date,
      note: note.trim(),
    ));
    await _persist();
  }

  Future<void> update(
    ExpenseTransaction old, {
    required double amount,
    required TransactionType type,
    required String category,
    required DateTime date,
    String note = '',
  }) async {
    _validate(amount, category);
    final index = _items.indexWhere((item) => item.id == old.id);
    if (index < 0) throw StateError('Transaction not found');
    _items[index] = ExpenseTransaction(
      id: old.id, amount: amount, type: type, category: category,
      date: date, note: note.trim(),
    );
    await _persist();
  }

  Future<void> delete(String id) async {
    _items.removeWhere((item) => item.id == id);
    await _persist();
  }

  void _validate(double amount, String category) {
    if (!amount.isFinite || amount <= 0) {
      throw ArgumentError('Amount must be greater than zero');
    }
    if (category.trim().isEmpty) throw ArgumentError('Category is required');
  }

  Future<void> _persist() async {
    _sort();
    await storage.saveTransactions(_items);
    notifyListeners();
  }

  void _sort() => _items.sort((a, b) => b.date.compareTo(a.date));
}
