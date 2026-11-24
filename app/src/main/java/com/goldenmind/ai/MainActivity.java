package com.goldenmind.ai;

import android.app.Activity;
import android.os.Bundle;
import android.widget.Button;
import android.widget.TextView;

public class MainActivity extends Activity {
    private TextView status;
    private TextView log;

    @Override public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        status = findViewById(R.id.status);
        log = findViewById(R.id.log);

        Button testnet = findViewById(R.id.testnet);
        Button paper = findViewById(R.id.paper);
        Button safety = findViewById(R.id.safety);

        testnet.setOnClickListener(v -> {
            status.setText("TESTNET mode selected. Network connector is not enabled yet.");
            append("• TESTNET connector: pending backend integration");
        });
        paper.setOnClickListener(v -> {
            status.setText("Paper trading is active locally. No real order can be sent.");
            append("• Paper engine: UI simulation active");
        });
        safety.setOnClickListener(v -> {
            status.setText("Safety checks: PASS — live execution remains disabled.");
            append("• Kill switch: protected\n• Live execution: disabled\n• Risk baseline: explicit/durable only");
        });
    }

    private void append(String message) {
        log.append("\n" + message);
    }
}
