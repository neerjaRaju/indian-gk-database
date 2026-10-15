import 'package:flutter/material.dart';

import 'database_service.dart';

const _ink = Color(0xFF173B35);
const _green = Color(0xFF246B54);
const _gold = Color(0xFFE5A23B);
const _paper = Color(0xFFF5F4EE);

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const BharatGkApp());
}

class BharatGkApp extends StatelessWidget {
  const BharatGkApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'Bharat GK',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          useMaterial3: true,
          scaffoldBackgroundColor: _paper,
          colorScheme: ColorScheme.fromSeed(seedColor: _green, primary: _green, secondary: _gold),
          appBarTheme: const AppBarTheme(backgroundColor: _paper, foregroundColor: _ink, elevation: 0),
          inputDecorationTheme: InputDecorationTheme(
            filled: true,
            fillColor: Colors.white,
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide.none),
          ),
        ),
        home: const DatabaseSplashScreen(),
      );
}

class DatabaseSplashScreen extends StatefulWidget {
  const DatabaseSplashScreen({super.key});

  @override
  State<DatabaseSplashScreen> createState() => _DatabaseSplashScreenState();
}

class _DatabaseSplashScreenState extends State<DatabaseSplashScreen> {
  final _service = DatabaseService();
  DatabaseSession? _session;
  String _status = 'Starting Bharat GK…';
  String? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _start();
  }

  Future<void> _start() async {
    setState(() {
      _loading = true;
      _error = null;
      _status = 'Checking for the latest database…';
    });
    try {
      final session = await _service.loadLatest(
        onStatus: (message) {
          if (mounted) setState(() => _status = message);
        },
      );
      if (mounted) setState(() => _session = session);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final session = _session;
    if (!_loading && session != null) return CategoryHome(session: session);
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: Padding(
              padding: const EdgeInsets.all(28),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Container(
                    width: 84,
                    height: 84,
                    decoration: BoxDecoration(color: _ink, borderRadius: BorderRadius.circular(24)),
                    child: const Icon(Icons.menu_book_rounded, color: Colors.white, size: 42),
                  ),
                  const SizedBox(height: 22),
                  const Text('BHARAT GK', style: TextStyle(color: _green, fontSize: 12, fontWeight: FontWeight.w900, letterSpacing: 2)),
                  const SizedBox(height: 10),
                  Text(
                    _loading ? _status : 'Question library unavailable',
                    textAlign: TextAlign.center,
                    style: const TextStyle(color: _ink, fontSize: 21, fontWeight: FontWeight.w800),
                  ),
                  const SizedBox(height: 20),
                  if (_loading)
                    const SizedBox(width: 220, child: LinearProgressIndicator(minHeight: 4))
                  else ...[
                    Text(_error ?? 'Connect to the internet, then retry.', textAlign: TextAlign.center),
                    const SizedBox(height: 16),
                    FilledButton.icon(onPressed: _start, icon: const Icon(Icons.refresh), label: const Text('Retry')),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class CategoryHome extends StatefulWidget {
  const CategoryHome({super.key, required this.session});
  final DatabaseSession session;

  @override
  State<CategoryHome> createState() => _CategoryHomeState();
}

class _CategoryHomeState extends State<CategoryHome> {
  String _language = 'en';
  String _search = '';
  late Future<List<CategoryInfo>> _categories;

  @override
  void initState() {
    super.initState();
    _categories = widget.session.categories(_language);
  }

  void _setLanguage(String language) {
    setState(() {
      _language = language;
      _categories = widget.session.categories(language);
    });
  }

  @override
  Widget build(BuildContext context) {
    final hindi = _language == 'hi';
    return Scaffold(
      appBar: AppBar(
        title: const Row(children: [
          Icon(Icons.menu_book_rounded, color: _green),
          SizedBox(width: 9),
          Text('Bharat GK', style: TextStyle(fontWeight: FontWeight.w900)),
        ]),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 14),
            child: SegmentedButton<String>(
              segments: const [ButtonSegment(value: 'en', label: Text('EN')), ButtonSegment(value: 'hi', label: Text('हि'))],
              selected: {_language},
              showSelectedIcon: false,
              onSelectionChanged: (selection) => _setLanguage(selection.first),
            ),
          ),
        ],
      ),
      body: FutureBuilder<List<CategoryInfo>>(
        future: _categories,
        builder: (context, snapshot) {
          if (snapshot.hasError) return Center(child: Text('Database error: ${snapshot.error}'));
          if (!snapshot.hasData) return const Center(child: CircularProgressIndicator());
          final all = snapshot.data!;
          final total = all.fold<int>(0, (sum, category) => sum + category.count);
          final categories = all.where((category) {
            final title = hindi ? category.nameHi : category.nameEn;
            return title.toLowerCase().contains(_search.toLowerCase()) || category.id.contains(_search.toLowerCase());
          });
          return ListView(
            padding: const EdgeInsets.fromLTRB(20, 14, 20, 28),
            children: [
              Container(
                padding: const EdgeInsets.all(22),
                decoration: BoxDecoration(color: _ink, borderRadius: BorderRadius.circular(8)),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(hindi ? 'आज का अभ्यास' : 'DAILY PRACTICE', style: const TextStyle(color: Color(0xFFFFD28A), fontSize: 11, fontWeight: FontWeight.w900, letterSpacing: 1.5)),
                  const SizedBox(height: 10),
                  Text(
                    hindi ? 'भारत को जानें।\nएक सवाल से शुरू करें।' : 'Know India better.\nOne question at a time.',
                    style: const TextStyle(color: Colors.white, fontSize: 26, height: 1.15, fontWeight: FontWeight.w900),
                  ),
                  const SizedBox(height: 17),
                  Wrap(spacing: 20, runSpacing: 8, children: [
                    _Stat(value: '${all.length}', label: hindi ? 'श्रेणियाँ' : 'categories'),
                    _Stat(value: '$total', label: hindi ? 'सवाल' : 'questions'),
                    _Stat(value: _language.toUpperCase(), label: hindi ? 'भाषा' : 'language'),
                  ]),
                ]),
              ),
              const SizedBox(height: 20),
              TextField(
                onChanged: (value) => setState(() => _search = value),
                decoration: InputDecoration(hintText: hindi ? 'श्रेणी खोजें' : 'Search categories', prefixIcon: const Icon(Icons.search)),
              ),
              const SizedBox(height: 22),
              Text(hindi ? 'श्रेणियाँ' : 'CATEGORIES', style: const TextStyle(color: _green, fontSize: 12, fontWeight: FontWeight.w900, letterSpacing: 1.4)),
              const SizedBox(height: 7),
              ...categories.map((category) => _CategoryRow(
                    category: category,
                    language: _language,
                    onTap: category.count == 0
                        ? null
                        : () => Navigator.push(context, MaterialPageRoute(
                              builder: (_) => QuizScreen(session: widget.session, category: category, language: _language),
                            )),
                  )),
              const SizedBox(height: 14),
              Text(hindi ? 'डेटाबेस ${widget.session.version}' : 'Database ${widget.session.version}', textAlign: TextAlign.center, style: const TextStyle(color: Colors.black45, fontSize: 11)),
            ],
          );
        },
      ),
    );
  }
}

class _Stat extends StatelessWidget {
  const _Stat({required this.value, required this.label});
  final String value;
  final String label;
  @override
  Widget build(BuildContext context) => Row(mainAxisSize: MainAxisSize.min, children: [
        Text(value, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w900, fontSize: 17)),
        const SizedBox(width: 5),
        Text(label, style: const TextStyle(color: Colors.white70, fontSize: 12)),
      ]);
}

class _CategoryRow extends StatelessWidget {
  const _CategoryRow({required this.category, required this.language, required this.onTap});
  final CategoryInfo category;
  final String language;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final title = language == 'hi' ? category.nameHi : category.nameEn;
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(8),
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 3),
        decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: Color(0x1F173B35)))),
        child: Row(children: [
          Container(
            width: 42,
            height: 42,
            alignment: Alignment.center,
            decoration: BoxDecoration(color: const Color(0xFFE3ECE5), borderRadius: BorderRadius.circular(8)),
            child: Text(title.isEmpty ? '•' : title.substring(0, 1), style: const TextStyle(color: _green, fontWeight: FontWeight.w900)),
          ),
          const SizedBox(width: 13),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(title, style: const TextStyle(color: _ink, fontWeight: FontWeight.w800, fontSize: 15)),
            const SizedBox(height: 3),
            Text('${category.count} ${language == 'hi' ? 'सवाल' : 'questions'}', style: const TextStyle(color: Colors.black54, fontSize: 12)),
          ])),
          const Icon(Icons.arrow_forward_rounded, size: 20, color: _green),
        ]),
      ),
    );
  }
}

class QuizScreen extends StatefulWidget {
  const QuizScreen({super.key, required this.session, required this.category, required this.language});
  final DatabaseSession session;
  final CategoryInfo category;
  final String language;

  @override
  State<QuizScreen> createState() => _QuizScreenState();
}

class _QuizScreenState extends State<QuizScreen> {
  late final Future<List<QuestionInfo>> _questions = widget.session.questions(widget.category.id, widget.language);
  int _index = 0;
  int? _answer;
  int _score = 0;

  @override
  Widget build(BuildContext context) {
    final hindi = widget.language == 'hi';
    return Scaffold(
      appBar: AppBar(title: Text(hindi ? widget.category.nameHi : widget.category.nameEn)),
      body: FutureBuilder<List<QuestionInfo>>(
        future: _questions,
        builder: (context, snapshot) {
          if (snapshot.hasError) return Center(child: Text('Could not load questions: ${snapshot.error}'));
          if (!snapshot.hasData) return const Center(child: CircularProgressIndicator());
          final questions = snapshot.data!;
          if (questions.isEmpty) return Center(child: Text(hindi ? 'इस भाषा में सवाल नहीं हैं।' : 'No questions in this language yet.'));
          if (_index >= questions.length) {
            return _QuizResult(score: _score, total: questions.length, hindi: hindi, onBack: () => Navigator.pop(context));
          }
          final question = questions[_index];
          final answered = _answer != null;
          return ListView(
            padding: const EdgeInsets.all(20),
            children: [
              Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
                Text('${_index + 1} / ${questions.length}', style: const TextStyle(color: _green, fontWeight: FontWeight.w900)),
                Text('${hindi ? 'स्कोर' : 'Score'} $_score', style: const TextStyle(color: _ink, fontWeight: FontWeight.w800)),
              ]),
              const SizedBox(height: 9),
              ClipRRect(borderRadius: BorderRadius.circular(6), child: LinearProgressIndicator(value: (_index + 1) / questions.length, minHeight: 6)),
              const SizedBox(height: 28),
              Text(question.difficulty.toUpperCase(), style: const TextStyle(color: _green, fontSize: 11, fontWeight: FontWeight.w900, letterSpacing: 1.5)),
              const SizedBox(height: 10),
              Text(question.question, style: const TextStyle(color: _ink, fontSize: 24, height: 1.24, fontWeight: FontWeight.w900)),
              const SizedBox(height: 22),
              ...List.generate(question.options.length, (index) {
                final correct = index == question.answerIndex;
                final chosen = index == _answer;
                final fill = !answered ? Colors.white : correct ? const Color(0xFFDCEFE2) : chosen ? const Color(0xFFF8E0DA) : Colors.white;
                return Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: InkWell(
                    onTap: answered ? null : () => setState(() { _answer = index; if (correct) _score++; }),
                    borderRadius: BorderRadius.circular(8),
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
                      decoration: BoxDecoration(color: fill, borderRadius: BorderRadius.circular(8), border: Border.all(color: answered && correct ? _green : const Color(0x1F173B35))),
                      child: Row(children: [
                        CircleAvatar(radius: 15, backgroundColor: answered && correct ? _green : const Color(0xFFE7E9E3), child: Text(String.fromCharCode(65 + index), style: TextStyle(color: answered && correct ? Colors.white : _ink, fontSize: 12, fontWeight: FontWeight.w900))),
                        const SizedBox(width: 12),
                        Expanded(child: Text(question.options[index], style: const TextStyle(color: _ink, fontWeight: FontWeight.w700, fontSize: 15))),
                        if (answered && correct) const Icon(Icons.check_circle, color: _green),
                        if (answered && chosen && !correct) const Icon(Icons.cancel, color: Color(0xFFB74A36)),
                      ]),
                    ),
                  ),
                );
              }),
              if (answered) ...[
                const SizedBox(height: 8),
                Container(padding: const EdgeInsets.all(16), decoration: BoxDecoration(color: const Color(0xFFE9EDE5), borderRadius: BorderRadius.circular(8)), child: Text(question.explanation, style: const TextStyle(color: _ink, height: 1.45))),
                const SizedBox(height: 18),
                FilledButton(
                  onPressed: () => setState(() { _index++; _answer = null; }),
                  child: Text(_index + 1 == questions.length ? (hindi ? 'परिणाम देखें' : 'See results') : (hindi ? 'अगला सवाल' : 'Next question')),
                ),
              ],
            ],
          );
        },
      ),
    );
  }
}

class _QuizResult extends StatelessWidget {
  const _QuizResult({required this.score, required this.total, required this.hindi, required this.onBack});
  final int score;
  final int total;
  final bool hindi;
  final VoidCallback onBack;

  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(28),
          child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
            const Icon(Icons.emoji_events_rounded, size: 64, color: _gold),
            const SizedBox(height: 20),
            Text(hindi ? 'अभ्यास पूरा हुआ' : 'Practice complete', style: const TextStyle(color: _ink, fontSize: 25, fontWeight: FontWeight.w900)),
            const SizedBox(height: 8),
            Text('$score / $total', style: const TextStyle(color: _green, fontSize: 38, fontWeight: FontWeight.w900)),
            const SizedBox(height: 22),
            FilledButton.icon(onPressed: onBack, icon: const Icon(Icons.grid_view_rounded), label: Text(hindi ? 'श्रेणियों पर वापस' : 'Back to categories')),
          ]),
        ),
      );
}