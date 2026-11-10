import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.OutputStream;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Small inventory REST API using only the JDK (no frameworks).
 * GET /api/items, GET /api/items/{id}, POST /api/items, PATCH /api/items/{id}, DELETE /api/items/{id}, GET /api/stock-value
 * Run: java -cp out InventoryApi 8080
 */
public final class InventoryApi {
    record Item(long id, String name, int qty, BigDecimal price) {
        String json() {
            return "{\"id\":" + id + ",\"name\":" + Json.quote(name) + ",\"qty\":" + qty + ",\"price\":" + price.toPlainString() + "}";
        }
    }

    static final class BadRequest extends RuntimeException {
        private static final long serialVersionUID = 1L;

        BadRequest(String message) { super(message); }
    }

    private final Map<Long, Item> items = new ConcurrentHashMap<>();
    private final AtomicLong nextId = new AtomicLong(1);
    private final HttpServer server;
    private final ExecutorService pool = Executors.newFixedThreadPool(8);

    public InventoryApi(int port) throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", port), 0);
        server.createContext("/api/", this::handle);
        server.setExecutor(pool);
    }

    public int start() {
        server.start();
        return server.getAddress().getPort();
    }

    public void stop() {
        server.stop(0);
        pool.shutdownNow();
    }

    private void handle(HttpExchange ex) throws IOException {
        try (ex) {
            String method = ex.getRequestMethod();
            String[] parts = ex.getRequestURI().getPath().replaceAll("/+$", "").split("/");  // "", "api", ...
            String body = new String(ex.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
            try {
                if (parts.length == 3 && parts[2].equals("stock-value") && method.equals("GET")) {
                    BigDecimal total = items.values().stream().map(i -> i.price().multiply(BigDecimal.valueOf(i.qty())))
                            .reduce(BigDecimal.ZERO, BigDecimal::add).setScale(2, RoundingMode.HALF_UP);
                    send(ex, 200, "{\"items\":" + items.size() + ",\"total\":" + total.toPlainString() + "}");
                } else if (parts.length == 3 && parts[2].equals("items")) {
                    switch (method) {
                        case "GET" -> {
                            List<Item> list = new ArrayList<>(items.values());
                            list.sort(Comparator.comparingLong(Item::id));
                            send(ex, 200, "[" + String.join(",", list.stream().map(Item::json).toList()) + "]");
                        }
                        case "POST" -> {
                            Map<String, Object> in = Json.parseObject(body);
                            long id = nextId.getAndIncrement();
                            Item item = new Item(id, name(in.get("name")), qty(in.get("qty")), price(in.get("price")));
                            items.put(id, item);
                            send(ex, 201, item.json());
                        }
                        default -> send(ex, 405, error("method not allowed"));
                    }
                } else if (parts.length == 4 && parts[2].equals("items")) {
                    long id = parseId(parts[3]);
                    Item item = items.get(id);
                    if (item == null) {
                        send(ex, 404, error("item " + id + " not found"));
                        return;
                    }
                    switch (method) {
                        case "GET" -> send(ex, 200, item.json());
                        case "PATCH" -> {
                            Map<String, Object> in = Json.parseObject(body);
                            Item updated = items.computeIfPresent(id, (key, current) -> new Item(id,
                                    in.containsKey("name") ? name(in.get("name")) : current.name(),
                                    in.containsKey("qty") ? qty(in.get("qty")) : current.qty(),
                                    in.containsKey("price") ? price(in.get("price")) : current.price()));
                            send(ex, updated == null ? 404 : 200,
                                    updated == null ? error("item " + id + " not found") : updated.json());
                        }
                        case "DELETE" -> {
                            items.remove(id);
                            send(ex, 204, null);
                        }
                        default -> send(ex, 405, error("method not allowed"));
                    }
                } else {
                    send(ex, 404, error("no such endpoint"));
                }
            } catch (BadRequest | IllegalArgumentException e) {
                send(ex, 400, error(e.getMessage()));
            }
        }
    }

    // --- validation -----------------------------------------------------------------------------------
    static String name(Object v) {
        if (!(v instanceof String s) || s.isBlank()) throw new BadRequest("name is required");
        if (s.length() > 100) throw new BadRequest("name is longer than 100 characters");
        return s.strip();
    }

    static int qty(Object v) {
        if (!(v instanceof BigDecimal d)) throw new BadRequest("qty must be a number");
        try {
            int q = d.intValueExact();
            if (q < 0) throw new BadRequest("qty cannot be negative");
            return q;
        } catch (ArithmeticException e) {
            throw new BadRequest("qty must be a whole number");
        }
    }

    static BigDecimal price(Object v) {
        if (!(v instanceof BigDecimal d)) throw new BadRequest("price must be a number");
        if (d.signum() < 0) throw new BadRequest("price cannot be negative");
        if (d.stripTrailingZeros().scale() > 2) throw new BadRequest("price has more than 2 decimals");
        return d.setScale(2, RoundingMode.UNNECESSARY);
    }

    static long parseId(String s) {
        try {
            return Long.parseLong(s);
        } catch (NumberFormatException e) {
            throw new BadRequest("id must be a number");
        }
    }

    static String error(String message) {
        return "{\"error\":" + Json.quote(message) + "}";
    }

    static void send(HttpExchange ex, int status, String json) throws IOException {
        if (json == null) {
            ex.sendResponseHeaders(status, -1);
            return;
        }
        byte[] out = json.getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set("Content-Type", "application/json; charset=utf-8");
        ex.sendResponseHeaders(status, out.length);
        try (OutputStream os = ex.getResponseBody()) {
            os.write(out);
        }
    }

    // --- minimal JSON for flat objects (strings, numbers, true/false/null) ------------------------------
    static final class Json {
        private final String s;
        private int i;

        private Json(String s) { this.s = s; }

        static Map<String, Object> parseObject(String text) {
            Json p = new Json(text == null ? "" : text);
            Map<String, Object> m = p.object();
            p.ws();
            if (p.i != p.s.length()) throw new IllegalArgumentException("invalid JSON: extra text after the object");
            return m;
        }

        static String quote(String v) {
            StringBuilder b = new StringBuilder("\"");
            for (char c : v.toCharArray()) {
                switch (c) {
                    case '"' -> b.append("\\\"");
                    case '\\' -> b.append("\\\\");
                    case '\n' -> b.append("\\n");
                    case '\r' -> b.append("\\r");
                    case '\t' -> b.append("\\t");
                    default -> {
                        if (c < 0x20) b.append(String.format("\\u%04x", (int) c));
                        else b.append(c);
                    }
                }
            }
            return b.append('"').toString();
        }

        private void ws() {
            while (i < s.length() && Character.isWhitespace(s.charAt(i))) i++;
        }

        private char peek() {
            ws();
            if (i >= s.length()) throw new IllegalArgumentException("invalid JSON: unexpected end");
            return s.charAt(i);
        }

        private void expect(char c) {
            if (peek() != c) throw new IllegalArgumentException("invalid JSON: expected '" + c + "' at position " + i);
            i++;
        }

        private Map<String, Object> object() {
            expect('{');
            Map<String, Object> m = new LinkedHashMap<>();
            if (peek() == '}') {
                i++;
                return m;
            }
            while (true) {
                String key = string();
                expect(':');
                m.put(key, value());
                if (peek() == ',') {
                    i++;
                    continue;
                }
                expect('}');
                return m;
            }
        }

        private Object value() {
            char c = peek();
            if (c == '"') return string();
            if (c == '-' || Character.isDigit(c)) return number();
            for (String word : new String[]{"true", "false", "null"}) {
                if (s.startsWith(word, i)) {
                    i += word.length();
                    return word.equals("null") ? null : Boolean.valueOf(word);
                }
            }
            throw new IllegalArgumentException("invalid JSON: unsupported value at position " + i);
        }

        private String string() {
            expect('"');
            StringBuilder b = new StringBuilder();
            while (i < s.length()) {
                char c = s.charAt(i++);
                if (c == '"') return b.toString();
                if (c != '\\') {
                    b.append(c);
                    continue;
                }
                if (i >= s.length()) break;
                char e = s.charAt(i++);
                switch (e) {
                    case '"', '\\', '/' -> b.append(e);
                    case 'n' -> b.append('\n');
                    case 't' -> b.append('\t');
                    case 'r' -> b.append('\r');
                    case 'b' -> b.append('\b');
                    case 'f' -> b.append('\f');
                    case 'u' -> {
                        if (i + 4 > s.length()) throw new IllegalArgumentException("invalid JSON: bad \\u escape");
                        b.append((char) Integer.parseInt(s.substring(i, i + 4), 16));
                        i += 4;
                    }
                    default -> throw new IllegalArgumentException("invalid JSON: bad escape \\" + e);
                }
            }
            throw new IllegalArgumentException("invalid JSON: unterminated string");
        }

        private BigDecimal number() {
            int start = i;
            if (s.charAt(i) == '-') i++;
            while (i < s.length() && "0123456789.eE+-".indexOf(s.charAt(i)) >= 0) i++;
            try {
                return new BigDecimal(s.substring(start, i));
            } catch (NumberFormatException e) {
                throw new IllegalArgumentException("invalid JSON: bad number at position " + start);
            }
        }
    }

    public static void main(String[] args) throws IOException {
        int port = args.length > 0 ? Integer.parseInt(args[0]) : 8080;
        InventoryApi api = new InventoryApi(port);
        System.out.println("Inventory API on http://127.0.0.1:" + api.start() + "/api/items");
    }
}
