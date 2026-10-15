// This is a basic Flutter widget test.
//
// To perform an interaction with a widget in your test, use the WidgetTester
// utility in the flutter_test package. For example, you can send tap and scroll
// gestures. You can also use WidgetTester to find child widgets in the widget
// tree, read text, and verify that the values of widget properties are correct.

import 'package:flutter_test/flutter_test.dart';

import 'package:indian_gk_app/main.dart';

void main() {
  testWidgets('shows database startup splash', (WidgetTester tester) async {
    await tester.pumpWidget(const BharatGkApp());
    expect(find.text('BHARAT GK'), findsOneWidget);
    expect(find.byType(BharatGkApp), findsOneWidget);
  });
}
