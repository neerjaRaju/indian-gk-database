import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:http/http.dart' as http;
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:sqflite/sqflite.dart';

const _latestReleaseApi =
  'https://api.github.com/repos/neerjaRaju/indian-gk-database/releases?per_page=100';

class DatabaseSession {
  const DatabaseSession(this.database, this.version);

  final Database database;
  final String version;

  Future<List<CategoryInfo>> categories(String language) async {
    final rows = await database.rawQuery('''
      SELECT c.id, c.name_en, c.name_hi, COUNT(q.id) AS question_count
      FROM categories c
      LEFT JOIN questions q ON q.category_id = c.id AND q.language = ?
      GROUP BY c.id, c.name_en, c.name_hi
      ORDER BY c.name_en COLLATE NOCASE
    ''', [language]);
    return rows.map(CategoryInfo.fromRow).toList();
  }

  Future<List<QuestionInfo>> questions(String categoryId, String language) async {
    final rows = await database.query(
      'questions',
      where: 'category_id = ? AND language = ?',
      whereArgs: [categoryId, language],
      orderBy: 'id',
    );
    return rows.map(QuestionInfo.fromRow).toList();
  }
}

class CategoryInfo {
  const CategoryInfo({
    required this.id,
    required this.nameEn,
    required this.nameHi,
    required this.count,
  });

  final String id;
  final String nameEn;
  final String nameHi;
  final int count;

  factory CategoryInfo.fromRow(Map<String, Object?> row) => CategoryInfo(
        id: row['id'] as String,
        nameEn: row['name_en'] as String,
        nameHi: row['name_hi'] as String,
        count: (row['question_count'] as num).toInt(),
      );
}

class QuestionInfo {
  const QuestionInfo({
    required this.id,
    required this.question,
    required this.options,
    required this.answerIndex,
    required this.explanation,
    required this.difficulty,
  });

  final String id;
  final String question;
  final List<String> options;
  final int answerIndex;
  final String explanation;
  final String difficulty;

  factory QuestionInfo.fromRow(Map<String, Object?> row) => QuestionInfo(
        id: row['id'] as String,
        question: row['question'] as String,
        options: (jsonDecode(row['options_json'] as String) as List).cast<String>(),
        answerIndex: (row['answer_index'] as num).toInt(),
        explanation: row['explanation'] as String,
        difficulty: row['difficulty'] as String,
      );
}

class DatabaseService {
  Future<DatabaseSession> loadLatest({required void Function(String) onStatus}) async {
    final directory = await getApplicationDocumentsDirectory();
    final databaseFile = File(p.join(directory.path, 'questions.sqlite3'));
    var version = 'cached';

    try {
      onStatus('Checking latest database…');
      final releaseResponse = await http
          .get(
            Uri.parse(_latestReleaseApi),
            headers: const {
              'Accept': 'application/vnd.github+json',
              'User-Agent': 'BharatGK-Android',
            },
          )
          .timeout(const Duration(seconds: 20));
      if (releaseResponse.statusCode != 200) {
        throw HttpException('GitHub release lookup failed (${releaseResponse.statusCode}).');
      }

      final releaseList = (jsonDecode(releaseResponse.body) as List).cast<Map<String, dynamic>>();
      Map<String, dynamic>? release;
      for (final candidate in releaseList) {
        if (candidate['draft'] != true && candidate['prerelease'] != true) {
          release = candidate;
          break;
        }
      }
      if (release == null) {
        for (final candidate in releaseList) {
          final tag = candidate['tag_name'] as String? ?? '';
          if (candidate['draft'] != true &&
              candidate['prerelease'] == true &&
              tag.startsWith('ai-draft-')) {
            release = candidate;
            break;
          }
        }
      }
      if (release == null) throw const FormatException('No database release is available yet.');
      final assets = (release['assets'] as List).cast<Map<String, dynamic>>();
      Map<String, dynamic>? databaseAsset;
      Map<String, dynamic>? manifestAsset;
      for (final asset in assets) {
        if (asset['name'] == 'questions.sqlite3') databaseAsset = asset;
        if (asset['name'] == 'manifest.json') manifestAsset = asset;
      }
      if (databaseAsset == null || manifestAsset == null) {
        throw const FormatException('Latest release is missing the database or manifest.');
      }

      onStatus('Downloading latest questions…');
      final manifestResponse = await http
          .get(Uri.parse(manifestAsset['browser_download_url'] as String))
          .timeout(const Duration(seconds: 30));
      if (manifestResponse.statusCode != 200) {
        throw HttpException('Could not download the database manifest.');
      }
      final manifest = jsonDecode(manifestResponse.body) as Map<String, dynamic>;
      final files = manifest['files'] as Map<String, dynamic>?;
      final sqliteEntry = files?['questions.sqlite3'] as Map<String, dynamic>?;
      final expectedHash = sqliteEntry?['sha256'] as String?;
      if (expectedHash == null) throw const FormatException('Database checksum is missing.');

      final response = await http
          .get(Uri.parse(databaseAsset['browser_download_url'] as String))
          .timeout(const Duration(minutes: 2));
      if (response.statusCode != 200) {
        throw HttpException('Database download failed (${response.statusCode}).');
      }
      final bytes = response.bodyBytes;
      if (sha256.convert(bytes).toString() != expectedHash) {
        throw const FormatException('Downloaded database checksum does not match.');
      }

      onStatus('Verifying database…');
      final temporaryFile = File('${databaseFile.path}.download');
      await temporaryFile.writeAsBytes(bytes, flush: true);
      final verificationDb = await openDatabase(temporaryFile.path, readOnly: true);
      try {
        final integrity = await verificationDb.rawQuery('PRAGMA integrity_check');
        if (integrity.first.values.first != 'ok') {
          throw const FormatException('Downloaded SQLite database failed integrity check.');
        }
        final tables = await verificationDb.rawQuery(
          "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('categories', 'questions')",
        );
        if (tables.length != 2) {
          throw const FormatException('Downloaded database schema is not supported.');
        }
      } finally {
        await verificationDb.close();
      }

      final backupFile = File('${databaseFile.path}.previous');
      if (await backupFile.exists()) await backupFile.delete();
      if (await databaseFile.exists()) await databaseFile.rename(backupFile.path);
      try {
        await temporaryFile.rename(databaseFile.path);
        if (await backupFile.exists()) await backupFile.delete();
      } catch (_) {
        if (await backupFile.exists() && !await databaseFile.exists()) {
          await backupFile.rename(databaseFile.path);
        }
        rethrow;
      }
      version = manifest['database_version'] as String? ?? release['tag_name'] as String? ?? 'latest';
      onStatus('Latest database is ready.');
    } catch (_) {
      if (!await databaseFile.exists()) rethrow;
      onStatus('Offline mode · using saved database');
    }

    final database = await openDatabase(databaseFile.path, readOnly: true);
    return DatabaseSession(database, version);
  }
}