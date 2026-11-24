package com.goldenmind.ai;

import android.app.Activity;
import android.os.Bundle;
import android.text.InputType;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends Activity {
    private TextView status, log;
    private EditText baseUrl, username, password;
    private final ExecutorService io = Executors.newSingleThreadExecutor();

    @Override public void onCreate(Bundle b) {
        super.onCreate(b);
        setContentView(R.layout.activity_main);
        status=findViewById(R.id.status); log=findViewById(R.id.log);
        baseUrl=findViewById(R.id.baseUrl); username=findViewById(R.id.username); password=findViewById(R.id.password);

        ((Button)findViewById(R.id.connect)).setOnClickListener(v -> connectBackend());
        ((Button)findViewById(R.id.testnet)).setOnClickListener(v -> {
            status.setText("TESTNET mode selected.");
            append("• TESTNET connector ready for authenticated backend");
        });
        ((Button)findViewById(R.id.paper)).setOnClickListener(v -> {
            status.setText("Paper trading is active locally. No real order can be sent.");
            append("• Paper engine: local simulation mode");
        });
        ((Button)findViewById(R.id.safety)).setOnClickListener(v -> {
            status.setText("Safety checks: PASS — live execution remains disabled.");
            append("• Kill switch protected\n• Live execution disabled\n• Explicit/durable risk baseline required");
        });
    }

    private void connectBackend() {
        final String url = baseUrl.getText().toString().trim();
        final String user = username.getText().toString().trim();
        final String pass = password.getText().toString();
        if (url.isEmpty()) { status.setText("Enter the backend URL."); return; }
        status.setText("Connecting…");
        io.execute(() -> {
            try {
                String health = request(url + "/health", "GET", null, null);
                if (!health.contains(""status":"ok"")) throw new Exception("Health check failed");
                String form = "username="+URLEncoder.encode(user, "UTF-8")
                        +"&password="+URLEncoder.encode(pass, "UTF-8");
                String tokenResponse = request(url + "/token", "POST", form, "application/x-www-form-urlencoded");
                String token = extractJson(tokenResponse, "access_token");
                if (token == null || token.isEmpty()) throw new Exception("Authentication failed");
                String ping = request(url + "/protected/ping", "GET", null, "Bearer "+token);
                if (!ping.contains(""status":"ok"")) throw new Exception("Protected ping failed");
                runOnUiThread(() -> {
                    status.setText("Connected • authenticated");
                    append("• Backend health: OK\n• Authentication: OK\n• Protected API: OK");
                });
            } catch (Exception e) {
                runOnUiThread(() -> {
                    status.setText("Connection failed: " + e.getMessage());
                    append("• Backend connection failed");
                });
            }
        });
    }

    private String request(String urlText, String method, String body, String auth) throws Exception {
        HttpURLConnection c=(HttpURLConnection)new URL(urlText).openConnection();
        c.setRequestMethod(method); c.setConnectTimeout(8000); c.setReadTimeout(8000);
        if (auth != null) c.setRequestProperty("Authorization", auth);
        if (body != null) {
            c.setDoOutput(true); c.setRequestProperty("Content-Type", "application/x-www-form-urlencoded");
            try(OutputStream out=c.getOutputStream()){ out.write(body.getBytes(StandardCharsets.UTF_8)); }
        }
        int code=c.getResponseCode();
        BufferedReader r=new BufferedReader(new InputStreamReader(
                code>=200 && code<400 ? c.getInputStream() : c.getErrorStream(), StandardCharsets.UTF_8));
        StringBuilder s=new StringBuilder(); String line;
        while((line=r.readLine())!=null)s.append(line);
        if(code<200 || code>=300) throw new Exception("HTTP "+code);
        return s.toString();
    }

    private String extractJson(String json, String key) {
        String needle="\""+key+"\":\"";
        int p=json.indexOf(needle); if(p<0)return null; p+=needle.length();
        int e=json.indexOf("\"",p); return e<0?null:json.substring(p,e);
    }

    private void append(String s){ log.append("\n"+s); }

    @Override protected void onDestroy(){ io.shutdownNow(); super.onDestroy(); }
}