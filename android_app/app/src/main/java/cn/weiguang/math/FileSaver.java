package cn.weiguang.math;

import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.Context;
import android.net.Uri;
import android.os.Environment;
import android.provider.MediaStore;
import android.webkit.CookieManager;

import java.io.InputStream;
import java.io.OutputStream;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import javax.net.ssl.HttpsURLConnection;

/** HTTPS-only streaming download; no storage permission, redirects or blob bridge. */
public final class FileSaver {
    public interface Callback {
        void finished(String message, boolean success);
    }

    private final ExecutorService executor = Executors.newSingleThreadExecutor();

    public void download(Context context, String origin, String url, Callback callback) {
        if (!UrlPolicy.approvedDownload(origin, url)) {
            callback.finished("只允许下载当前微光数学服务器中的视频和记录", false);
            return;
        }
        executor.execute(() -> {
            Uri saved = null;
            HttpsURLConnection connection = null;
            try {
                boolean video = url.contains("/videos/") && url.endsWith("/download");
                String filename = "微光数学_" + System.currentTimeMillis() +
                        (video ? ".mp4" : "_全部微调记录.json");
                String mime = video ? "video/mp4" : "application/json";

                connection = (HttpsURLConnection) new URL(url).openConnection();
                connection.setConnectTimeout(12000);
                connection.setReadTimeout(90000);
                connection.setInstanceFollowRedirects(false);
                connection.setRequestProperty("Accept", mime);
                String cookie = CookieManager.getInstance().getCookie(url);
                if (cookie != null && !cookie.isEmpty()) {
                    connection.setRequestProperty("Cookie", cookie);
                }
                if (connection.getResponseCode() != 200) {
                    throw new IllegalStateException(
                            "下载请求未成功（HTTP " + connection.getResponseCode() + "）");
                }
                String received = connection.getContentType();
                if (received == null || !received.toLowerCase().startsWith(mime)) {
                    throw new IllegalStateException("下载内容类型与请求不符");
                }

                ContentResolver resolver = context.getContentResolver();
                ContentValues values = new ContentValues();
                values.put(MediaStore.Downloads.DISPLAY_NAME, filename);
                values.put(MediaStore.Downloads.MIME_TYPE, mime);
                values.put(MediaStore.Downloads.RELATIVE_PATH,
                        Environment.DIRECTORY_DOWNLOADS + "/微光数学");
                values.put(MediaStore.Downloads.IS_PENDING, 1);
                saved = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);
                if (saved == null) throw new IllegalStateException("无法创建下载文件");
                try (InputStream input = connection.getInputStream();
                     OutputStream output = resolver.openOutputStream(saved)) {
                    if (output == null) throw new IllegalStateException("无法写入下载文件");
                    byte[] buffer = new byte[64 * 1024];
                    int count;
                    while ((count = input.read(buffer)) != -1) {
                        output.write(buffer, 0, count);
                    }
                }
                ContentValues published = new ContentValues();
                published.put(MediaStore.Downloads.IS_PENDING, 0);
                resolver.update(saved, published, null, null);
                callback.finished("已保存至 下载/微光数学", true);
            } catch (Exception exception) {
                if (saved != null) context.getContentResolver().delete(saved, null, null);
                callback.finished("下载失败：" + exception.getMessage(), false);
            } finally {
                if (connection != null) connection.disconnect();
            }
        });
    }

    public void shutdown() {
        executor.shutdownNow();
    }
}
