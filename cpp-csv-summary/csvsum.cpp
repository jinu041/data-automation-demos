// csvsum: group a CSV file by one column and total another, with clear errors for bad rows.
// Build: g++ -std=c++17 -O2 -Wall -Wextra -o csvsum csvsum.cpp
// Usage: csvsum sales.csv --group Region --sum Amount [--out summary.csv]
#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <sstream>
#include <string>
#include <vector>

namespace {

struct Totals {
    long count = 0;
    long double sum = 0;
    double min = 0, max = 0;
};

std::string trim(const std::string& s) {
    const auto b = s.find_first_not_of(" \t\r\n");
    if (b == std::string::npos) return "";
    return s.substr(b, s.find_last_not_of(" \t\r\n") - b + 1);
}

enum class CsvStatus { complete, incomplete, malformed };

// Splits one CSV record; incomplete quotes let the caller append the next line.
CsvStatus split_csv(const std::string& rec, std::vector<std::string>& out) {
    out.clear();
    std::string cur;
    bool quoted = false, closed = false;
    for (size_t i = 0; i < rec.size(); ++i) {
        const char c = rec[i];
        if (quoted) {
            if (c != '"') cur += c;
            else if (i + 1 < rec.size() && rec[i + 1] == '"') { cur += '"'; ++i; }
            else { quoted = false; closed = true; }
        } else if (c == ',') { out.push_back(cur); cur.clear(); closed = false; }
        else if (c == '"') {
            if (!cur.empty() || closed) return CsvStatus::malformed;
            quoted = true;
        } else if (c != '\r') {
            if (closed) return CsvStatus::malformed;
            cur += c;
        }
    }
    out.push_back(cur);
    return quoted ? CsvStatus::incomplete : CsvStatus::complete;
}

// "1,234.50", "$12", "(3.00)" -> number. Anything else that isn't fully numeric is rejected.
bool parse_number(std::string s, double& v) {
    s.erase(std::remove_if(s.begin(), s.end(), [](char c) { return c == ' ' || c == ',' || c == '$'; }), s.end());
    const bool negative = s.size() > 2 && s.front() == '(' && s.back() == ')';
    if (negative) s = s.substr(1, s.size() - 2);
    if (s.empty()) return false;
    char* end = nullptr;
    v = std::strtod(s.c_str(), &end);
    if (*end != '\0' || !std::isfinite(v)) return false;
    if (negative) v = -v;
    return true;
}

std::string csv_field(const std::string& s) {
    if (s.find_first_of(",\"\n") == std::string::npos) return s;
    std::string q = "\"";
    for (char c : s) q += (c == '"') ? std::string("\"\"") : std::string(1, c);
    return q + "\"";
}

int column(const std::vector<std::string>& header, const std::string& name) {
    for (size_t i = 0; i < header.size(); ++i)
        if (trim(header[i]) == name) return static_cast<int>(i);
    std::cerr << "error: no column named '" << name << "'. Columns:";
    for (const auto& h : header) std::cerr << " [" << trim(h) << "]";
    std::cerr << "\n";
    return -1;
}

}  // namespace

int main(int argc, char** argv) {
    std::string path, group_by, sum_of, out_path;
    for (int i = 1; i < argc; ++i) {
        const std::string a = argv[i];
        if ((a == "--group" || a == "--sum" || a == "--out") && i + 1 < argc) {
            (a == "--group" ? group_by : a == "--sum" ? sum_of : out_path) = argv[++i];
        } else if (path.empty() && a.rfind("--", 0) != 0) {
            path = a;
        } else {
            std::cerr << "unknown argument: " << a << "\n";
            return 1;
        }
    }
    if (path.empty() || group_by.empty() || sum_of.empty()) {
        std::cerr << "usage: csvsum file.csv --group COLUMN --sum COLUMN [--out summary.csv]\n";
        return 1;
    }
    std::ifstream in(path, std::ios::binary);
    if (!in) {
        std::cerr << "error: cannot open " << path << "\n";
        return 1;
    }

    std::vector<std::string> header, fields;
    std::string line, rec;
    long line_no = 0, rec_start = 0, bad = 0;
    int gi = -1, si = -1;
    std::map<std::string, Totals> groups;
    while (std::getline(in, line)) {
        ++line_no;
        if (rec.empty()) {
            rec_start = line_no;
            if (line_no == 1 && line.rfind("\xEF\xBB\xBF", 0) == 0) line.erase(0, 3);  // UTF-8 BOM
        }
        rec += rec.empty() ? line : "\n" + line;
        const auto status = split_csv(rec, fields);
        if (status == CsvStatus::incomplete) continue;  // quoted field spans lines
        rec.clear();
        if (status == CsvStatus::malformed) {
            std::cerr << "line " << rec_start << ": malformed CSV quoting\n";
            if (header.empty()) return 1;
            ++bad;
            continue;
        }
        if (header.empty()) {
            header = fields;
            if ((gi = column(header, group_by)) < 0 || (si = column(header, sum_of)) < 0) return 1;
            continue;
        }
        if (fields.size() == 1 && trim(fields[0]).empty()) continue;  // blank line
        if (fields.size() != header.size()) {
            std::cerr << "line " << rec_start << ": " << fields.size() << " fields, header has " << header.size() << "\n";
            ++bad;
            continue;
        }
        double v = 0;
        if (!parse_number(fields[si], v)) {
            std::cerr << "line " << rec_start << ": " << sum_of << " is not a number ('" << trim(fields[si]) << "')\n";
            ++bad;
            continue;
        }
        auto& t = groups[trim(fields[gi])];
        t.min = t.count ? std::min(t.min, v) : v;
        t.max = t.count ? std::max(t.max, v) : v;
        t.sum += v;
        ++t.count;
    }
    if (!rec.empty()) {
        std::cerr << "line " << rec_start << ": quote is never closed\n";
        ++bad;
    }
    if (header.empty()) {
        std::cerr << "error: " << path << " is empty\n";
        return 1;
    }

    std::vector<std::pair<std::string, Totals>> rows(groups.begin(), groups.end());
    std::sort(rows.begin(), rows.end(), [](const auto& a, const auto& b) { return a.second.sum > b.second.sum; });
    Totals all;
    std::ostringstream csv;
    csv << csv_field(group_by) << ",Rows,Total,Average,Min,Max\n";
    std::cout << std::left << std::setw(22) << group_by << std::right << std::setw(6) << "Rows" << std::setw(14) << "Total"
              << std::setw(12) << "Average" << std::setw(12) << "Min" << std::setw(12) << "Max" << "\n"
              << std::fixed << std::setprecision(2);
    for (const auto& [name, t] : rows) {
        const double avg = static_cast<double>(t.sum / t.count);
        std::cout << std::left << std::setw(22) << name.substr(0, 21) << std::right << std::setw(6) << t.count
                  << std::setw(14) << static_cast<double>(t.sum) << std::setw(12) << avg << std::setw(12) << t.min
                  << std::setw(12) << t.max << "\n";
        csv << csv_field(name) << "," << t.count << "," << std::fixed << std::setprecision(2) << static_cast<double>(t.sum)
            << "," << avg << "," << t.min << "," << t.max << "\n";
        all.min = all.count ? std::min(all.min, t.min) : t.min;
        all.max = all.count ? std::max(all.max, t.max) : t.max;
        all.count += t.count;
        all.sum += t.sum;
    }
    std::cout << std::left << std::setw(22) << "TOTAL" << std::right << std::setw(6) << all.count << std::setw(14)
              << static_cast<double>(all.sum) << "\n";
    if (bad) std::cerr << bad << " row(s) skipped, see messages above\n";
    if (!out_path.empty()) {
        std::ofstream out(out_path, std::ios::binary);
        if (!out) {
            std::cerr << "error: cannot open " << out_path << "\n";
            return 1;
        }
        out << csv.str();
        if (!out) {
            std::cerr << "error: cannot write " << out_path << "\n";
            return 1;
        }
        out.close();
        if (!out) {
            std::cerr << "error: cannot close " << out_path << "\n";
            return 1;
        }
        std::cout << "summary written to " << out_path << "\n";
    }
    return 0;
}
