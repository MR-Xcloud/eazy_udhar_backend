<?php
$uri = $_SERVER['REQUEST_URI'] ?? '/';
$path = parse_url($uri, PHP_URL_PATH) ?: '/';
$query = parse_url($uri, PHP_URL_QUERY);

// When opened as /index.php or /proxy.php, forward "/" to the Node app.
if ($path === '/index.php' || $path === '/proxy.php') {
    $uri = '/' . ($query ? ('?' . $query) : '');
}

$target = 'http://127.0.0.1:3100' . $uri;
$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';

$ch = curl_init($target);
curl_setopt($ch, CURLOPT_CUSTOMREQUEST, $method);
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
curl_setopt($ch, CURLOPT_HEADER, true);
curl_setopt($ch, CURLOPT_FOLLOWLOCATION, false);
curl_setopt($ch, CURLOPT_TIMEOUT, 60);

$headers = [];
if (function_exists('getallheaders')) {
    foreach (getallheaders() as $k => $v) {
        $lk = strtolower($k);
        if ($lk === 'host' || $lk === 'accept-encoding') {
            continue;
        }
        $headers[] = $k . ': ' . $v;
    }
}
$headers[] = 'X-Forwarded-Proto: https';
$headers[] = 'X-Forwarded-Host: admin.eazyudhar.com';
curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);

if (in_array($method, ['POST', 'PUT', 'PATCH', 'DELETE'], true)) {
    curl_setopt($ch, CURLOPT_POSTFIELDS, file_get_contents('php://input'));
}

$response = curl_exec($ch);
if ($response === false) {
    http_response_code(502);
    echo 'Bad gateway: ' . curl_error($ch);
    exit;
}

$headerSize = curl_getinfo($ch, CURLINFO_HEADER_SIZE);
$status = curl_getinfo($ch, CURLINFO_HTTP_CODE);
curl_close($ch);

$headerStr = substr($response, 0, $headerSize);
$body = substr($response, $headerSize);
http_response_code($status);

foreach (explode("\r\n", $headerStr) as $line) {
    if ($line === '' || stripos($line, 'HTTP/') === 0) {
        continue;
    }
    if (stripos($line, 'Transfer-Encoding:') === 0) {
        continue;
    }
    if (stripos($line, 'Connection:') === 0) {
        continue;
    }
    if (stripos($line, 'Content-Length:') === 0) {
        continue;
    }
    header($line, false);
}
echo $body;
