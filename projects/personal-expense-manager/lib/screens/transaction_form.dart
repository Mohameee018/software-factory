import 'package:flutter/material.dart';
import '../controllers/expense_controller.dart';
import '../models/expense_transaction.dart';

class TransactionForm extends StatefulWidget {
  const TransactionForm({super.key, required this.controller, this.initial});
  final ExpenseController controller;
  final ExpenseTransaction? initial;

  @override
  State<TransactionForm> createState() => _TransactionFormState();
}

class _TransactionFormState extends State<TransactionForm> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _amount;
  late final TextEditingController _note;
  late TransactionType _type;
  late String _category;
  late DateTime _date;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    final item = widget.initial;
    _amount = TextEditingController(text: item?.amount.toString() ?? '');
    _note = TextEditingController(text: item?.note ?? '');
    _type = item?.type ?? TransactionType.expense;
    _category = item?.category ?? ExpenseController.categories.first;
    _date = item?.date ?? DateTime.now();
  }

  @override
  void dispose() {
    _amount.dispose();
    _note.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(
          title: Text(widget.initial == null ? 'Add transaction' : 'Edit transaction'),
        ),
        body: Form(
          key: _formKey,
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              TextFormField(
                controller: _amount,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                decoration: const InputDecoration(labelText: 'Amount'),
                validator: (value) {
                  final amount = double.tryParse(value ?? '');
                  return amount == null || amount <= 0
                      ? 'Enter an amount greater than zero'
                      : null;
                },
              ),
              const SizedBox(height: 16),
              DropdownButtonFormField<TransactionType>(
                initialValue: _type,
                decoration: const InputDecoration(labelText: 'Type'),
                items: const [
                  DropdownMenuItem(value: TransactionType.expense, child: Text('Expense')),
                  DropdownMenuItem(value: TransactionType.income, child: Text('Income')),
                ],
                onChanged: (value) => setState(() => _type = value!),
              ),
              const SizedBox(height: 16),
              DropdownButtonFormField<String>(
                initialValue: _category,
                decoration: const InputDecoration(labelText: 'Category'),
                items: ExpenseController.categories
                    .map((item) => DropdownMenuItem(value: item, child: Text(item)))
                    .toList(),
                onChanged: (value) => setState(() => _category = value!),
              ),
              const SizedBox(height: 16),
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text(
                  'Date: ' + _date.year.toString() + '-' +
                  _date.month.toString().padLeft(2, '0') + '-' +
                  _date.day.toString().padLeft(2, '0'),
                ),
                trailing: const Icon(Icons.calendar_month),
                onTap: _pickDate,
              ),
              TextFormField(
                controller: _note,
                maxLines: 3,
                decoration: const InputDecoration(labelText: 'Note'),
              ),
              const SizedBox(height: 24),
              FilledButton.icon(
                onPressed: _saving ? null : _save,
                icon: _saving
                    ? const SizedBox.square(
                        dimension: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.save),
                label: Text(_saving ? 'Saving...' : 'Save'),
              ),
            ],
          ),
        ),
      );

  Future<void> _pickDate() async {
    final picked = await showDatePicker(
      context: context,
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
      initialDate: _date,
    );
    if (picked != null) setState(() => _date = picked);
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _saving = true);
    try {
      final amount = double.parse(_amount.text);
      final item = widget.initial;
      if (item == null) {
        await widget.controller.add(
          amount: amount, type: _type, category: _category,
          date: _date, note: _note.text,
        );
      } else {
        await widget.controller.update(
          item, amount: amount, type: _type, category: _category,
          date: _date, note: _note.text,
        );
      }
      if (mounted) Navigator.pop(context);
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Could not save transaction: ' + error.toString())),
        );
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }
}
