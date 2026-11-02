package cn.weiguang.math;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.net.http.SslError;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.inputmethod.InputMethodManager;
import android.content.Context;
import android.webkit.CookieManager;
import android.webkit.PermissionRequest;
import android.webkit.SslErrorHandler;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import javax.net.ssl.HttpsURLConnection;

/**
 * WeiGuang Math Android client: same HTML and FastAPI API as desktop/web.
 *
 * Android never executes MathTeacher/Manim locally or stores provider API keys.
 * Strict HTTPS + exact origin, no JavaScript bridge, verified health endpoint,
 * system ZIP chooser and authenticated MP4/JSON downloads.
 */
public final class MainActivity extends Activity {
    private static final String PREFS = "weiguang_android_connection";
    private static final String URL_KEY = "server_origin";
    private static final int FILE_PICKER = 6204;
    private static final int INK = Color.rgb(30, 31, 33);
    private static final int MUTED = Color.rgb(112, 112, 112);

    private final ExecutorService network = Executors.newSingleThreadExecutor();
    private final Handler ui = new Handler(Looper.getMainLooper());
    private final FileSaver fileSaver = new FileSaver();

    private FrameLayout root;
    private EditText urlField;
    private TextView message;
    private Button connectButton;
    private WebView browser;
    private android.webkit.ValueCallback<Uri[]> fileCallback;
    private String currentOrigin;
    private ProgressBar loadIndicator;
    private boolean closed;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(Color.WHITE);
        getWindow().setNavigationBarColor(Color.WHITE);
        // Do not request WindowInsetsController before the decor view exists:
        // on Android 15 PhoneWindow.getInsetsController can throw NPE in onCreate.
        root = new FrameLayout(this);
        root.setBackgroundColor(Color.WHITE);
        if (Build.VERSION.SDK_INT >= 35) {
            root.setOnApplyWindowInsetsListener((view, insets) -> {
                android.graphics.Insets bars = insets.getInsets(
                        WindowInsets.Type.systemBars());
                view.setPadding(bars.left, bars.top, bars.right, bars.bottom);
                return insets;
            });
        }
        setContentView(root);
        if (Build.VERSION.SDK_INT >= 30) {
            root.post(() -> {
                if (closed) return;
                WindowInsetsController controller = root.getWindowInsetsController();
                if (controller != null) {
                    int light = WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS
                            | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS;
                    controller.setSystemBarsAppearance(light, light);
                }
            });
        }
        showLauncher();
        String saved = getPreferences().getString(URL_KEY, "");
        if (!saved.isEmpty()) connect(saved);
    }

    private android.content.SharedPreferences getPreferences() {
        return getSharedPreferences(PREFS, MODE_PRIVATE);
    }

    private int dp(float value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private GradientDrawable background(int color, int stroke, int radius) {
        GradientDrawable result = new GradientDrawable();
        result.setColor(color);
        result.setCornerRadius(dp(radius));
        if (stroke != 0) result.setStroke(dp(1), stroke);
        return result;
    }

    private TextView text(String value, int size, int color, boolean bold) {
        TextView label = new TextView(this);
        label.setText(value);
        label.setTextSize(size);
        label.setTextColor(color);
        if (bold) label.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        return label;
    }

    private Button action(String value, boolean primary) {
        Button button = new Button(this);
        button.setText(value);
        button.setAllCaps(false);
        button.setTextSize(14);
        button.setTextColor(primary ? Color.WHITE : INK);
        button.setBackground(background(
                primary ? INK : Color.WHITE,
                primary ? 0 : Color.rgb(223, 223, 223), 9));
        button.setMinHeight(dp(48));
        button.setPadding(dp(16), dp(10), dp(16), dp(10));
        return button;
    }

    private void showLauncher() {
        browser = null;
        currentOrigin = null;
        root.removeAllViews();
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setClipToPadding(false);
        LinearLayout column = new LinearLayout(this);
        column.setOrientation(LinearLayout.VERTICAL);
        column.setPadding(dp(28), dp(52), dp(28), dp(35));
        scroll.addView(column);
        root.addView(scroll, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT));

        ImageView logo = new ImageView(this);
        logo.setImageResource(R.drawable.ic_brand_mark);
        logo.setContentDescription("微光数学书页与星芒标志");
        LinearLayout.LayoutParams logoLayout = new LinearLayout.LayoutParams(
                dp(92), dp(92));
        logoLayout.bottomMargin = dp(26);
        column.addView(logo, logoLayout);

        TextView title = text("微光数学", 29, INK, true);
        column.addView(title);
        TextView subtitle = text("考研数学 · 教学视频工作台", 13, MUTED, false);
        LinearLayout.LayoutParams subtitleParams =
                new LinearLayout.LayoutParams(-1, -2);
        subtitleParams.topMargin = dp(7);
        subtitleParams.bottomMargin = dp(42);
        column.addView(subtitle, subtitleParams);

        TextView label = text("服务器 HTTPS 地址", 14, INK, true);
        LinearLayout.LayoutParams labelParams =
                new LinearLayout.LayoutParams(-1, -2);
        labelParams.bottomMargin = dp(12);
        column.addView(label, labelParams);

        urlField = new EditText(this);
        urlField.setSingleLine(true);
        urlField.setTextSize(15);
        urlField.setTextColor(INK);
        urlField.setHintTextColor(Color.rgb(160,160,160));
        urlField.setHint("https://math.example.com");
        urlField.setInputType(
                InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        urlField.setBackground(background(Color.WHITE,
                Color.rgb(214, 214, 214), 9));
        urlField.setPadding(dp(14), dp(14), dp(14), dp(14));
        urlField.setText(getPreferences().getString(URL_KEY, ""));
        column.addView(urlField, new LinearLayout.LayoutParams(-1, dp(53)));

        connectButton = action("连接工作台", true);
        LinearLayout.LayoutParams connectParams =
                new LinearLayout.LayoutParams(-1, dp(49));
        connectParams.topMargin = dp(18);
        column.addView(connectButton, connectParams);
        connectButton.setOnClickListener(view -> connect(
                urlField.getText().toString()));

        message = text("手机连接已部署的微光数学后端，视频在服务器生成。", 12, MUTED, false);
        message.setLineSpacing(dp(3), 1f);
        LinearLayout.LayoutParams messageParams =
                new LinearLayout.LayoutParams(-1, -2);
        messageParams.topMargin = dp(23);
        column.addView(message, messageParams);
    }

    private void setMessage(String value, boolean error) {
        if (message != null) {
            message.setText(value);
            message.setTextColor(error ? Color.rgb(148, 55, 55) : MUTED);
        }
    }

    private void connect(String raw) {
        final String origin;
        try {
            origin = UrlPolicy.normalizeServer(raw);
        } catch (IllegalArgumentException error) {
            setMessage(error.getMessage(), true);
            return;
        }
        connectButton.setEnabled(false);
        setMessage("正在连接服务器…", false);
        network.execute(() -> {
            try {
                verifyServer(origin);
                ui.post(() -> {
                    if (closed) return;
                    getPreferences().edit().putString(URL_KEY, origin).apply();
                    openWeb(origin);
                });
            } catch (Exception error) {
                ui.post(() -> {
                    if (closed) return;
                    if (connectButton != null) connectButton.setEnabled(true);
                    setMessage("连接失败：" + error.getMessage(), true);
                });
            }
        });
    }

    private static void verifyServer(String origin) throws Exception {
        HttpsURLConnection connection =
                (HttpsURLConnection) new URL(origin + "/health").openConnection();
        try {
            connection.setConnectTimeout(9000);
            connection.setReadTimeout(9000);
            connection.setInstanceFollowRedirects(false);
            connection.setRequestProperty("Accept", "application/json");
            if (connection.getResponseCode() != 200) {
                throw new IllegalStateException("服务器响应 HTTP " +
                        connection.getResponseCode());
            }
            try (InputStream stream = connection.getInputStream();
                 ByteArrayOutputStream bytes = new ByteArrayOutputStream()) {
                byte[] buffer = new byte[1024];
                int size;
                while ((size = stream.read(buffer)) != -1) {
                    if (bytes.size() + size > 8192) {
                        throw new IllegalStateException("服务器健康检查响应无效");
                    }
                    bytes.write(buffer, 0, size);
                }
                JSONObject doc = new JSONObject(
                        bytes.toString(StandardCharsets.UTF_8.name()));
                if (!"ok".equals(doc.optString("status"))
                        || !"weiguang-math".equals(doc.optString("service"))) {
                    throw new IllegalStateException("不是微光数学后台");
                }
            }
        } finally {
            connection.disconnect();
        }
    }

    private void openWeb(String origin) {
        root.removeAllViews();
        currentOrigin = origin;
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setBackgroundColor(Color.WHITE);
        root.addView(layout, new FrameLayout.LayoutParams(-1, -1));

        LinearLayout toolbar = new LinearLayout(this);
        toolbar.setGravity(Gravity.CENTER_VERTICAL);
        toolbar.setPadding(dp(15), dp(3), dp(8), dp(3));
        toolbar.setBackgroundColor(Color.WHITE);
        layout.addView(toolbar, new LinearLayout.LayoutParams(-1, dp(51)));
        TextView brand = text("微光数学", 16, INK, true);
        toolbar.addView(brand, new LinearLayout.LayoutParams(0, -2, 1f));
        TextView refresh = text("刷新", 13, MUTED, false);
        refresh.setGravity(Gravity.CENTER);
        refresh.setPadding(dp(13), dp(8), dp(13), dp(8));
        refresh.setOnClickListener(view -> { if (browser != null) browser.reload(); });
        toolbar.addView(refresh);
        TextView change = text("服务器", 13, MUTED, false);
        change.setGravity(Gravity.CENTER);
        change.setPadding(dp(13), dp(8), dp(13), dp(8));
        change.setOnClickListener(view -> {
            if (browser != null) {
                WebView previous = browser;
                showLauncher();
                previous.destroy();
            }
        });
        toolbar.addView(change);

        View border = new View(this);
        border.setBackgroundColor(Color.rgb(238, 238, 238));
        layout.addView(border, new LinearLayout.LayoutParams(-1, dp(1)));

        loadIndicator = new ProgressBar(this,null,
                android.R.attr.progressBarStyleHorizontal);
        loadIndicator.setMax(100);
        loadIndicator.setProgress(0);
        layout.addView(loadIndicator, new LinearLayout.LayoutParams(-1, dp(2)));

        WebView view = new WebView(this);
        browser = view;
        WebView.setWebContentsDebuggingEnabled(false);
        WebSettings settings = view.getSettings();
        settings.setJavaScriptEnabled(true); // Required by existing WeiGuang SPA.
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(true); // System picker content URIs only.
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setSupportMultipleWindows(false);
        settings.setGeolocationEnabled(false);
        settings.setMediaPlaybackRequiresUserGesture(true);
        settings.setSupportZoom(false);
        settings.setTextZoom(100);
        CookieManager manager = CookieManager.getInstance();
        manager.setAcceptCookie(true);
        manager.setAcceptThirdPartyCookies(view, false);

        view.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest request) {
                String next = request.getUrl().toString();
                if (!UrlPolicy.sameOrigin(origin, next)) {
                    Toast.makeText(MainActivity.this,
                            "出于安全考虑，仅能打开当前服务器", Toast.LENGTH_SHORT).show();
                    return true;
                }
                return false;
            }

            @Override
            public WebResourceResponse shouldInterceptRequest(
                    WebView v, WebResourceRequest request) {
                String url = request.getUrl().toString();
                if (!UrlPolicy.sameOrigin(origin, url)) {
                    return new WebResourceResponse("text/plain", "utf-8",
                            new ByteArrayInputStream(new byte[0]));
                }
                return null;
            }

            @Override
            public void onReceivedSslError(WebView v, SslErrorHandler handler,
                                           SslError error) {
                handler.cancel(); // Never bypass hostname/certificate checks.
                ui.post(() -> Toast.makeText(MainActivity.this,
                        "HTTPS 证书验证失败，请检查服务器证书", Toast.LENGTH_LONG).show());
            }

            @Override
            public void onReceivedError(WebView v, WebResourceRequest request,
                                        WebResourceError error) {
                if (request.isForMainFrame()) {
                    ui.post(() -> Toast.makeText(MainActivity.this,
                            "工作台暂时无法访问，请检查服务器", Toast.LENGTH_LONG).show());
                }
            }
        });

        view.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView v, int progress) {
                if (loadIndicator != null) {
                    loadIndicator.setProgress(progress);
                    loadIndicator.setVisibility(progress >= 100 ? View.GONE : View.VISIBLE);
                }
            }

            @Override
            public boolean onShowFileChooser(WebView v,
                    android.webkit.ValueCallback<Uri[]> callback,
                    FileChooserParams params) {
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = callback;
                try {
                    Intent intent = params.createIntent();
                    intent.addCategory(Intent.CATEGORY_OPENABLE);
                    startActivityForResult(intent, FILE_PICKER);
                    return true;
                } catch (ActivityNotFoundException error) {
                    fileCallback = null;
                    callback.onReceiveValue(null);
                    Toast.makeText(MainActivity.this,
                            "没有可用的文件选择器", Toast.LENGTH_SHORT).show();
                    return false;
                }
            }

            @Override
            public void onPermissionRequest(PermissionRequest request) {
                request.deny();
            }
        });

        view.setDownloadListener((url, userAgent, contentDisposition,
                                  mimeType, contentLength) -> {
            if (!UrlPolicy.approvedDownload(origin, url)) {
                Toast.makeText(this, "此下载地址未通过安全检查", Toast.LENGTH_LONG).show();
                return;
            }
            Toast.makeText(this, "开始下载…", Toast.LENGTH_SHORT).show();
            fileSaver.download(getApplicationContext(), origin, url,
                    (result, success) -> ui.post(() -> {
                        if (!closed) Toast.makeText(this, result,
                                Toast.LENGTH_LONG).show();
                    }));
        });

        layout.addView(view, new LinearLayout.LayoutParams(-1, 0, 1f));
        view.loadUrl(origin + "/");
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != FILE_PICKER) return;
        android.webkit.ValueCallback<Uri[]> callback = fileCallback;
        fileCallback = null;
        if (callback != null) callback.onReceiveValue(
                WebChromeClient.FileChooserParams.parseResult(resultCode, data));
    }

    @Override
    public void onBackPressed() {
        if (browser != null && browser.canGoBack()) {
            browser.goBack();
        } else if (browser != null) {
            WebView previous = browser;
            showLauncher();
            previous.destroy();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onDestroy() {
        closed = true;
        if (fileCallback != null) fileCallback.onReceiveValue(null);
        fileCallback = null;
        if (browser != null) {
            browser.destroy();
            browser = null;
        }
        fileSaver.shutdown();
        network.shutdownNow();
        super.onDestroy();
    }
}
