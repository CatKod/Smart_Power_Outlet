#pragma once

#include <Arduino.h>

#ifndef DEBUG_MODE
#define DEBUG_MODE 1
#endif

#if DEBUG_MODE
#define LOGF(...) Serial.printf(__VA_ARGS__)
#define LOGLN(msg) Serial.println(msg)
#define LOG(msg) Serial.print(msg)
#else
#define LOGF(...) ((void)0)
#define LOGLN(msg) ((void)0)
#define LOG(msg) ((void)0)
#endif
