public with sharing class CloudBridgeApiService {
    private static final Integer TIMEOUT_MS = 120000;

    private static String normalizeBaseUrl(String rawUrl) {
        if (String.isBlank(rawUrl)) {
            throw new AuraHandledException('CloudBridge_Base_Url label is empty. Set it to a backend URL or callout:NamedCredential.');
        }

        String trimmed = rawUrl.trim();
        if (trimmed.toLowerCase().endsWith('/api/v1/docs')) {
            trimmed = trimmed.substring(0, trimmed.length() - '/api/v1/docs'.length());
        }
        if (trimmed.toLowerCase().endsWith('/api/v1')) {
            trimmed = trimmed.substring(0, trimmed.length() - '/api/v1'.length());
        }
        if (trimmed.endsWith('/')) {
            trimmed = trimmed.substring(0, trimmed.length() - 1);
        }
        return trimmed;
    }

    public static String getBaseUrl() {
        return normalizeBaseUrl(Label.CloudBridge_Base_Url);
    }

    public static String buildEndpoint(String path) {
        String base = getBaseUrl();
        String cleanPath = path;
        if (!cleanPath.startsWith('/')) {
            cleanPath = '/' + cleanPath;
        }
        return base + cleanPath;
    }

    public static HttpResponse send(String method, String path, Object bodyObj) {
        HttpRequest req = new HttpRequest();
        req.setMethod(method);
        req.setEndpoint(buildEndpoint(path));
        req.setHeader('Content-Type', 'application/json');
        req.setHeader('Accept', 'application/json');
        req.setTimeout(TIMEOUT_MS);

        if (!String.isBlank(Label.CloudBridge_Api_Key)) {
            req.setHeader('x-api-key', Label.CloudBridge_Api_Key);
        }

        if (bodyObj != null) {
            req.setBody(JSON.serialize(bodyObj));
        }

        Http http = new Http();
        return http.send(req);
    }

    public static Map<String, Object> parseJsonBody(HttpResponse res) {
        String body = res.getBody();
        if (String.isBlank(body)) {
            return new Map<String, Object>();
        }
        Object parsed = JSON.deserializeUntyped(body);
        if (parsed instanceof Map<String, Object>) {
            return (Map<String, Object>) parsed;
        }
        return new Map<String, Object>{ 'data' => parsed };
    }

    public static void throwIfNotOk(HttpResponse res) {
        Integer code = res.getStatusCode();
        if (code >= 200 && code < 300) {
            return;
        }

        String body = res.getBody();
        String bodyLower = String.isBlank(body) ? '' : body.toLowerCase();
        if (code == 503 && bodyLower.contains('application is not available')) {
            throw new AuraHandledException(
                'Cloud Bridge API is unavailable (503). Verify CloudBridge_Base_Url route and ensure backend pods are running. Current base URL: ' + getBaseUrl()
            );
        }

        String message = 'Cloud Bridge API error: ' + String.valueOf(code);
        try {
            Map<String, Object> err = parseJsonBody(res);
            if (err.containsKey('detail') && err.get('detail') != null) {
                message += ' - ' + String.valueOf(err.get('detail'));
            } else if (err.containsKey('error') && err.get('error') != null) {
                message += ' - ' + String.valueOf(err.get('error'));
            }
        } catch (Exception ignoreErr) {
            if (!String.isBlank(body)) {
                String compactBody = body.replaceAll('<[^>]+>', ' ').replaceAll('\\s+', ' ').trim();
                if (compactBody.length() > 300) {
                    compactBody = compactBody.substring(0, 300) + '...';
                }
                message += ' - ' + compactBody;
            }
        }

        throw new AuraHandledException(message);
    }
}
