import 'package:flutter/material.dart';
import '../controllers/expense_controller.dart';
import '../models/expense_transaction.dart';
import 'transaction_form.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.controller});
  final ExpenseController controller;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  ExpenseController get c => widget.controller;

  @override
  void initState() {
    super.initState();
    c.addListener(_refresh);
  }

  @override
  void dispose() {
    c.removeListener(_refresh);
    super.dispose();
  }

  void _refresh() => setState(() {});

  @override
  Widget build(BuildContext context) {
    final items = c.visible;
    return Scaffold(
      appBar: AppBar(title: const Text('Expense Manager')),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _openForm(),
        icon: const Icon(Icons.add),
        label: const Text('Add'),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 100),
        children: [
          _summary(context),
          const SizedBox(height: 16),
          TextField(
            onChanged: c.setQuery,
            decoration: const InputDecoration(
              prefixIcon: Icon(Icons.search),
              hintText: 'Search category or note',
            ),
          ),
          const SizedBox(height: 8),
          SegmentedButton<TransactionType?>(
            segments: const [
              ButtonSegment(value: null, label: Text('All')),
              ButtonSegment(value: TransactionType.income, label: Text('Income')),
              ButtonSegment(value: TransactionType.expense, label: Text('Expense')),
            ],
            selected: {c.filter},
            onSelectionChanged: (value) => c.setFilter(value.first),
          ),
          const SizedBox(height: 16),
          if (items.isEmpty)
            const Card(
              child: Padding(
                padding: EdgeInsets.all(32),
                child: Column(
                  children: [
                    Icon(Icons.receipt_long, size: 48),
                    SizedBox(height: 12),
                    Text('No transactions found'),
                  ],
                ),
              ),
            )
          else
            ...items.map((item) => _tile(item)),
        ],
      ),
    );
  }

  Widget _summary(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Balance'),
                  const SizedBox(height: 6),
                  Text(c.balance.toStringAsFixed(2),
                      style: Theme.of(context).textTheme.headlineMedium),
                ],
              ),
            ),
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(child: _metric('Income', c.income)),
              const SizedBox(width: 10),
              Expanded(child: _metric('Expenses', c.expenses)),
            ],
          ),
        ],
      );

  Widget _metric(String label, double value) => Card(
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label),
              const SizedBox(height: 4),
              Text(value.toStringAsFixed(2),
                  style: const TextStyle(fontWeight: FontWeight.bold)),
            ],
          ),
        ),
      );

  Widget _tile(ExpenseTransaction item) {
    final income = item.type == TransactionType.income;
    return Card(
      child: ListTile(
        leading: CircleAvatar(
          child: Icon(income ? Icons.arrow_downward : Icons.arrow_upward),
        ),
        title: Text(item.category),
        subtitle: Text(item.note.isEmpty
            ? item.date.toLocal().toString().split(' ').first
            : item.note),
        trailing: PopupMenuButton<String>(
          onSelected: (value) async {
            if (value == 'edit') {
              await _openForm(item);
            } else if (value == 'delete') {
              await c.delete(item.id);
            }
          },
          itemBuilder: (_) => const [
            PopupMenuItem(value: 'edit', child: Text('Edit')),
            PopupMenuItem(value: 'delete', child: Text('Delete')),
          ],
        ),
      ),
    );
  }

  Future<void> _openForm([ExpenseTransaction? item]) async {
    await Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => TransactionForm(controller: c, initial: item),
      ),
    );
  }
}
