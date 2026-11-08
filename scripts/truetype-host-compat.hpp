// Host-only compatibility: glibc has a struct member named __unused.
// Parse its headers before defining Android's parameter annotation.
#pragma once
#include <pthread.h>
#include <linux/types.h>
#define __unused __attribute__((unused))
