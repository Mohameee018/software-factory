import 'package:flutter_test/flutter_test.dart';
import 'package:personal_expense_manager/controllers/expense_controller.dart';
import 'package:personal_expense_manager/models/expense_transaction.dart';

class FakeStorage {
  List<ExpenseTransaction> items = [];
  List<ExpenseTransaction> loadTransactions() => List.of(items);
  Future<void> saveTransactions(List<ExpenseTransaction> value) async {
    items = List.of(value);
  }
}

void main() {
  test('CRUD updates totals and persists', () async {
    final storage = FakeStorage();
    final controller = ExpenseController(_Adapter(storage));
    await controller.add(
      amount: 100,
      type: TransactionType.income,
      category: 'Salary',
      date: DateTime(2026, 1, 1),
    );
    await controller.add(
      amount: 25,
      type: TransactionType.expense,
      category: 'Food',
      date: DateTime(2026, 1, 2),
    );
    expect(controller.income, 100);
    expect(controller.expenses, 25);
    expect(controller.balance, 75);
    expect(storage.items, hasLength(2));

    final item = controller.all.last;
    await controller.update(
      item,
      amount: 30,
      type: item.type,
      category: item.category,
      date: item.date,
    );
    expect(controller.expenses, 30);
    await controller.delete(item.id);
    expect(controller.expenses, 0);
  });

  test('validation rejects zero and negative amount', () {
    final controller = ExpenseController(_Adapter(FakeStorage()));
    expect(
      () => controller.add(
        amount: 0,
        type: TransactionType.expense,
        category: 'Food',
        date: DateTime.now(),
      ),
      throwsArgumentError,
    );
    expect(
      () => controller.add(
        amount: -1,
        type: TransactionType.expense,
        category: 'Food',
        date: DateTime.now(),
      ),
      throwsArgumentError,
    );
  });

  test('search and filter work together', () async {
    final controller = ExpenseController(_Adapter(FakeStorage()));
    await controller.add(
      amount: 10,
      type: TransactionType.expense,
      category: 'Food',
      date: DateTime.now(),
      note: 'Lunch',
    );
    await controller.add(
      amount: 100,
      type: TransactionType.income,
      category: 'Salary',
      date: DateTime.now(),
      note: 'Job',
    );
    controller.setQuery('lunch');
    expect(controller.visible, hasLength(1));
    controller.setQuery('');
    controller.setFilter(TransactionType.income);
    expect(controller.visible, hasLength(1));
    expect(controller.visible.first.category, 'Salary');
  });
}

class _Adapter {
  _Adapter(this.inner);
  final FakeStorage inner;
  List<ExpenseTransaction> loadTransactions() => inner.loadTransactions();
  Future<void> saveTransactions(List<ExpenseTransaction> value) =>
      inner.saveTransactions(value);
}
