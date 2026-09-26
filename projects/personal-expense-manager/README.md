# Personal Expense Manager

Flutter benchmark app for the AI Software Factory.

## Features
- Dashboard balance, income, expenses and recent transactions.
- Add, edit and delete transactions.
- Amount, type, category, date and note.
- Search and type filtering.
- Local persistence with SharedPreferences.
- Validation and empty/error states.
- English UI with localization-ready structure.

## Run
flutter pub get
flutter run

## Test
flutter test

## Architecture
models -> services -> controllers -> screens.

## Security
No secrets, network credentials or paid services. Dependencies are limited to Flutter SDK, SharedPreferences and intl.

## Known limitations
No cloud sync/authentication. Currency and localization can be extended later.
