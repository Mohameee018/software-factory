import 'package:flutter/material.dart';
import 'controllers/expense_controller.dart';
import 'screens/home_screen.dart';
import 'services/storage_service.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final storage = StorageService();
  await storage.init();
  runApp(ExpenseApp(controller: ExpenseController(storage)));
}

class ExpenseApp extends StatelessWidget {
  const ExpenseApp({super.key, required this.controller});
  final ExpenseController controller;

  @override
  Widget build(BuildContext context) => MaterialApp(
        debugShowCheckedModeBanner: false,
        title: 'Expense Manager',
        theme: ThemeData(
          colorScheme: ColorScheme.fromSeed(seedColor: Colors.indigo),
          useMaterial3: true,
          inputDecorationTheme: const InputDecorationTheme(
            border: OutlineInputBorder(),
          ),
        ),
        home: HomeScreen(controller: controller),
      );
}
