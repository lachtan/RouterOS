#!/usr/bin/php
<?php

require_once(dirname(__FILE__)."/routeros.class.php");

if($argc < 3) {
  die("usage: ${argv[0]} <login>:<password>@<host> <destination1>@<speed>@<protocol>...\n");
}

// get args
list($login, $host) = explode('@', $argv[1], 2);
if($host) {
  list($login, $password) = explode(':', $login, 2);
}
else {
  $host = $login;
  $login = "admin";
  $password = "";
}

// connect to server
$conn = RouterOS::connect($host, $login, $password) or die("couldn't connect to $login@$host\n");
$conn->setTimeout(60);

// structures
$dests = array();
$status = array();
$current = array();
$average = array();
$percent = array();
$tags = array();

// start btest
for($i = 2; $i < $argc; ++$i) {
  list($dest, $speed, $protocol) = explode("@", $argv[$i]);

  if(!$speed)
    $speed = 0;
  if(!$protocol)
    $protocol = "tcp";
    
  $name = gethostbynamel($dest);
  if($name === FALSE) 
      die("couldn't resolve $dest!\n");
  $name = $name[0];
      
  if($dests[$name])
    die("destination $dest already defined!\n");  
 
  $tag = $conn->btest($name, $speed, $protocol, btestCallback);
  if($tag === FALSE)
    continue;
  
  $tags[$tag] = $name;
  $dests[$name] = array("dest" => $dest, "speed" => $speed, "protocol" => $protocol);
}

// print header
ncurses_init();
ncurses_nl();
printStatus();

// dispatch messages
$continue = TRUE;
$conn->dispatch($continue);

exit;

function btestCallback($conn, $state, $results) {
  global $dests, $tags, $status, $current, $average, $percent;

  // done message
  if($state == TRUE && !$results)
    return;
  
  // find destination
  $dest = $tags[$results[".tag"]];
  if($dest === FALSE)
    return;
  
  // trap message
  if($state == FALSE) {
    if($results["message"] == "interrupted")
      return;
      
    // state changed
    if($status[$dest] != $results["message"]) {
      $status[$dest] = $results["message"];
      printStatus();
    }
    return;
  }
  
  // not running
  if($results["status"] != "running") {
    // state changed
    if($status[$dest] != $results["status"]) {
      $status[$dest] = $results["status"];
      printStatus();
    }
    
    // restart btest (in error state)
    if($results["status"] != "connecting") {
      $conn->cancel($results[".tag"]);
      $tag = $conn->btest($dest, $dests[$dest]["speed"], $dests[$dest]["protocol"], btestCallback);
      if($tag !== FALSE)
        $tags[$tag] = $dest;
    }
    return;
  }
 
  // running get results
  $status[$dest] = $results["status"];
  $current[$dest] = $results["tx-current"];
  $average[$dest] = $results["tx-10-second-average"];
  $percent[$dest] = round(100 * $results["tx-10-second-average"] / stringToBytes($dests[$dest]["speed"], 1000), 1);
  printStatus();
}

function stringToBytes($data, $multi = 1024) {
  $value = floatval($data);
  switch(substr(strtolower($data), -1)) {
    case 'g':
      $value *= $multi;
    case 'm':
      $value *= $multi;
    case 'k':
      $value *= $multi;
  }
  return $value;
}

function bytesToString($data, $multi = 1024, $postfix = "") {
  $data = intval($data);

  if($data < $multi) {
    return round($data, 0) . $postfix;
  }
  if($data < $multi*$multi) {
    return round($data/$multi, 1) . "k$postfix";
  }
  if($data < $multi*$multi*$multi) {
    return round($data/$multi/$multi, 1) . "M$postfix";
  }
  return round($dat /$multi/$multi/$multi, 1) . "G$postfix";
}

function getTime() {
  static $startTime;
  if(!$startTime)
    $startTime = microtime(TRUE);
  return round(microtime(TRUE) - $startTime, 1);
}

function printTable($header, $line) {
  $sizes = array();
  foreach($header as $h)
    $sizes[$h] = strlen($h);

  foreach($line as $v)
    foreach($header as $h)
      $sizes[$h] = max($sizes[$h], strlen($v[$h]));

  $out = "== ";
  foreach($header as $h)
    $out .= str_pad($h, $sizes[$h])." == ";
  $out .= "\n";  

  foreach($line as $v) {
    $out .= "-- ";
    foreach($header as $h)
      $out .= @str_pad($v[$h], $sizes[$h])." -- ";
    $out .= "\n";
  }
  return $out;
}

function printStatus() {
  global $dests, $status, $current, $average, $percent;

  // calculate
  $header = array("host", "speed", "proto", "status", "current", "average", "%");
  $lines = array();
  
  $averageSum = 0;

  foreach($dests as $dest=>$desc) {
    $lines[] = array("host"=>$desc["dest"], "speed"=>$desc["speed"], "proto"=>$desc["protocol"], 
"status"=>$status[$dest], "current"=>bytesToString($current[$dest], 1000), "average"=>bytesToString($average[$dest], 1000), "%"=>$percent[$dest]);
    $averageSum += $average[$dest];
  }
 
  // draw on screen
  ncurses_clear();
  ncurses_move(0, 0);
  ncurses_addstr("btester\ntime: ".getTime()."\naverage: ".bytesToString($averageSum, 1000)."\n\n");
  ncurses_addstr(printTable($header, $lines));
  ncurses_refresh();
}
