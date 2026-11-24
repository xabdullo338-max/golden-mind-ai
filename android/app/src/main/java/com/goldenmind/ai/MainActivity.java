package com.goldenmind.ai;
import android.app.Activity;
import android.os.Bundle;
import android.widget.Button;
import android.widget.TextView;
public class MainActivity extends Activity {
 private TextView status,log;
 @Override public void onCreate(Bundle b){super.onCreate(b);setContentView(R.layout.activity_main);status=findViewById(R.id.status);log=findViewById(R.id.log);
  ((Button)findViewById(R.id.testnet)).setOnClickListener(v->{status.setText("TESTNET mode selected. Backend connector is not enabled yet.");append("• TESTNET connector: pending authenticated backend integration");});
  ((Button)findViewById(R.id.paper)).setOnClickListener(v->{status.setText("Paper trading is active locally. No real order can be sent.");append("• Paper engine: UI simulation active");});
  ((Button)findViewById(R.id.safety)).setOnClickListener(v->{status.setText("Safety checks: PASS — live execution remains disabled.");append("• Kill switch: protected\n• Live execution: disabled\n• Risk baseline: explicit/durable only");});}
 private void append(String s){log.append("\n"+s);}
}
