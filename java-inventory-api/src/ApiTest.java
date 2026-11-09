import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.IntStream;

/** Starts the API on a free port and checks every endpoint over real HTTP. Run: java -cp out ApiTest */
public final class ApiTest {
    static final HttpClient http = HttpClient.newHttpClient();
    static String base;
    static int passed;

    static HttpResponse<String> call(String method, String path, String body) throws Exception {
        HttpRequest.Builder b = HttpRequest.newBuilder(URI.create(base + path)).header("Content-Type", "application/json");
        b.method(method, body == null ? HttpRequest.BodyPublishers.noBody() : HttpRequest.BodyPublishers.ofString(body));
        return http.send(b.build(), HttpResponse.BodyHandlers.ofString());
    }

    static void check(boolean ok, String what, HttpResponse<String> r) {
        if (!ok) throw new AssertionError(what + " -> " + (r == null ? "" : r.statusCode() + " " + r.body()));
        passed++;
        System.out.println("ok  " + what);
    }

    public static void main(String[] args) throws Exception {
        InventoryApi api = new InventoryApi(0);
        base = "http://127.0.0.1:" + api.start();
        try {
            var r = call("POST", "/api/items", "{\"name\":\"Mug\",\"qty\":3,\"price\":7.50}");
            check(r.statusCode() == 201 && r.body().equals("{\"id\":1,\"name\":\"Mug\",\"qty\":3,\"price\":7.50}"), "POST creates an item", r);
            r = call("POST", "/api/items", "{\"name\":\"Tea \\\"Earl Grey\\\"\",\"qty\":10,\"price\":1.25}");
            check(r.statusCode() == 201 && r.body().contains("\"name\":\"Tea \\\"Earl Grey\\\"\""), "POST keeps escaped quotes", r);

            for (String[] bad : List.of(
                    new String[]{"{\"qty\":1,\"price\":2}", "name is required"},
                    new String[]{"{\"name\":\"X\",\"qty\":-1,\"price\":2}", "qty cannot be negative"},
                    new String[]{"{\"name\":\"X\",\"qty\":1.5,\"price\":2}", "qty must be a whole number"},
                    new String[]{"{\"name\":\"X\",\"qty\":1,\"price\":2.345}", "price has more than 2 decimals"},
                    new String[]{"{\"name\":\"X\",\"qty\":1,\"price\":\"2\"}", "price must be a number"},
                    new String[]{"{\"name\":\"X\",", "invalid JSON"},
                    new String[]{"{\"name\":\"X\",\"qty\":1,\"price\":2} extra", "extra text"})) {
                r = call("POST", "/api/items", bad[0]);
                check(r.statusCode() == 400 && r.body().contains(bad[1]), "POST rejects: " + bad[1], r);
            }

            r = call("GET", "/api/items", null);
            check(r.statusCode() == 200 && r.body().startsWith("[{\"id\":1,") && r.body().contains("\"id\":2"), "GET lists items in id order", r);
            r = call("GET", "/api/items/999", null);
            check(r.statusCode() == 404 && r.body().contains("item 999 not found"), "GET unknown id is 404", r);
            r = call("GET", "/api/items/abc", null);
            check(r.statusCode() == 400, "GET non-numeric id is 400", r);
            r = call("PATCH", "/api/items/1", "{\"qty\":4}");
            check(r.statusCode() == 200 && r.body().contains("\"qty\":4") && r.body().contains("\"price\":7.50"), "PATCH changes only qty", r);
            r = call("GET", "/api/stock-value", null);
            check(r.statusCode() == 200 && r.body().equals("{\"items\":2,\"total\":42.50}"), "stock value = 4 x 7.50 + 10 x 1.25", r);
            r = call("PUT", "/api/items", "{}");
            check(r.statusCode() == 405, "unsupported method is 405", r);
            r = call("DELETE", "/api/items/2", null);
            check(r.statusCode() == 204, "DELETE removes an item", r);
            r = call("GET", "/api/items/2", null);
            check(r.statusCode() == 404, "deleted item is gone", r);

            // 50 parallel POSTs must get 50 different ids
            List<CompletableFuture<HttpResponse<String>>> futures = IntStream.range(0, 50).mapToObj(n ->
                    http.sendAsync(HttpRequest.newBuilder(URI.create(base + "/api/items"))
                            .POST(HttpRequest.BodyPublishers.ofString("{\"name\":\"Box " + n + "\",\"qty\":1,\"price\":0.10}")).build(),
                            HttpResponse.BodyHandlers.ofString())).toList();
            Set<String> ids = new HashSet<>();
            Matcher m;
            for (var f : futures) {
                m = Pattern.compile("\"id\":(\\d+)").matcher(f.get().body());
                if (f.get().statusCode() == 201 && m.find()) ids.add(m.group(1));
            }
            check(ids.size() == 50, "50 parallel POSTs get 50 unique ids", null);
            r = call("GET", "/api/stock-value", null);
            check(r.body().equals("{\"items\":51,\"total\":35.00}"), "stock value after parallel POSTs (4 x 7.50 + 50 x 0.10)", r);
        } finally {
            api.stop();
        }
        System.out.println(passed + " checks passed");
    }
}
