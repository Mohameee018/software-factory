enum TransactionType { income, expense }

class ExpenseTransaction {
  const ExpenseTransaction({
    required this.id,
    required this.amount,
    required this.type,
    required this.category,
    required this.date,
    this.note = '',
  });

  final String id;
  final double amount;
  final TransactionType type;
  final String category;
  final DateTime date;
  final String note;

  double get signedAmount =>
      type == TransactionType.income ? amount : -amount;

  Map<String, dynamic> toJson() => {
        'id': id,
        'amount': amount,
        'type': type.name,
        'category': category,
        'date': date.toIso8601String(),
        'note': note,
      };

  factory ExpenseTransaction.fromJson(Map<String, dynamic> json) =>
      ExpenseTransaction(
        id: json['id'] as String,
        amount: (json['amount'] as num).toDouble(),
        type: TransactionType.values.byName(json['type'] as String),
        category: json['category'] as String,
        date: DateTime.parse(json['date'] as String),
        note: (json['note'] as String?) ?? '',
      );
}
