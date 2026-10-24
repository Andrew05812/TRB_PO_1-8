<?php
declare(strict_types=1);
require_once __DIR__ . '/../src/bootstrap.php';

header('Location: ' . (empty($_SESSION['user_id']) ? 'login.php' : 'dashboard.php'));
exit;
