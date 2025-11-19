# Salary Service Performance Optimization Guide

## Current Performance Issue

The `get_salary_schedule_for_district()` function in [backend/services/salary_service.py](../backend/services/salary_service.py) takes ~1 second to return all salary data for a district.

## Root Causes

### 1. **No Caching** (Primary Issue)
- Same data fetched repeatedly from DynamoDB
- Every API request performs a full query
- Lambda cold starts compound the problem

### 2. **Excessive Data Transfer**
```python
# Line 98: Fetches ALL attributes for every record
response = table.query(KeyConditionExpression=key_condition)
```

For a district with 5 years × 25 edu/credit combos × 15 steps = **1,875 records**, this transfers:
- All DynamoDB attributes (including GSI keys, calculated flags, metadata)
- ~500KB-1MB of data over the network

### 3. **Inefficient In-Memory Processing**
```python
# Lines 108-117: Creates new dict for EVERY salary record
for item in items:
    year_period = f"{item['school_year']}#{item['period']}"
    schedules[year_period].append({
        'education': item.get('education'),
        'is_calculated': item.get('is_calculated', False),
        # ... 4 more fields with type conversions
    })
```

For 1,875 records:
- 1,875 dictionary allocations
- 1,875 × 6 = 11,250 dict key assignments
- 3,750 type conversions (int/float)
- 1,875 string concatenations for year_period

### 4. **Redundant Response Formatting**
```python
# Lines 121-128: Iterates again to format response
for year_period, salaries in schedules.items():
    year, period = year_period.split('#', 1)
    result.append({...})
```

## Optimization Strategies (Ranked by Impact)

### 🥇 #1: Add Caching (80% improvement expected)

**Impact:** Reduces ~1s to ~50-100ms for cached requests

**Implementation:**
- Lambda container-level cache (persists across invocations)
- 60-second TTL
- Cache key: `{district_id}#{year}`

```python
# Use the optimized version from salary_service_optimized.py
from services.salary_service_optimized import get_salary_schedule_for_district_optimized

result = get_salary_schedule_for_district_optimized(
    main_table,
    district_id,
    year,
    use_cache=True  # Enable caching
)
```

**Cache Invalidation:**
```python
# Call after uploading new salary data
from services.salary_service_optimized import invalidate_salary_cache

invalidate_salary_cache(district_id)  # Specific district
# or
invalidate_salary_cache()  # Clear all
```

### 🥈 #2: Use DynamoDB ProjectionExpression (15% improvement)

**Impact:** Reduces data transfer by 40-60%

```python
response = table.query(
    KeyConditionExpression=key_condition,
    ProjectionExpression='school_year,period,education,credits,#s,salary,is_calculated,is_calculated_from',
    ExpressionAttributeNames={'#s': 'step'}
)
```

**Why it helps:**
- Avoids transferring GSI keys (GSI1PK, GSI1SK, GSI2PK, GSI2SK)
- Reduces payload from ~1MB to ~400KB
- Less JSON parsing on Lambda side

### 🥉 #3: Optimize In-Memory Processing (5% improvement)

**Current (slow):**
```python
for item in items:
    schedules[year_period].append({
        'education': item.get('education'),
        'credits': int(item.get('credits', 0)),  # Multiple .get() calls
        'step': int(item.get('step', 0)),
        'salary': float(item.get('salary', 0))
    })
```

**Optimized (fast):**
```python
for item in items:
    schedules[year_period].append({
        'education': item['education'],  # Direct access
        'credits': int(item['credits']),  # No default needed
        'step': int(item['step']),
        'salary': float(item['salary'])
    })
```

### #4: DynamoDB DAX (Distributed Cache) - **AWS Cost**

**Impact:** ~300ms → ~5ms for cached queries

**Pros:**
- Microsecond response times
- Automatic cache invalidation
- Scales horizontally
- No code changes needed

**Cons:**
- **Cost:** ~$0.25/hour ($180/month) for smallest node
- Requires VPC configuration
- Overkill for small datasets

**When to use:**
- High traffic (1000+ requests/min)
- Multiple Lambda functions sharing cache
- Budget allows for dedicated caching layer

### #5: DynamoDB Global Tables - **For Multi-Region Only**

**Impact:** Reduces cross-region latency

Only relevant if you deploy to multiple AWS regions.

## Recommended Implementation Plan

### Phase 1: Quick Wins (30 minutes)
1. ✅ Replace `get_salary_schedule_for_district` with optimized version
2. ✅ Add ProjectionExpression to reduce data transfer
3. ✅ Enable Lambda container caching

**Expected result:** ~1000ms → ~200ms (uncached), ~50ms (cached)

### Phase 2: Cache Management (1 hour)
1. Add cache invalidation to salary upload endpoints
2. Add cache stats logging
3. Monitor cache hit rate in CloudWatch

### Phase 3: Advanced (Optional, 2-4 hours)
1. Add batch prefetch for district lists
2. Implement streaming responses for very large datasets
3. Consider DAX if traffic justifies cost

## Code Changes Required

### Option A: Drop-in Replacement (Minimal Changes)

**File:** `backend/services/salary_service.py`

Replace lines 70-130 with the optimized version:

```python
# Add at top of file
_salary_cache = {}
_cache_ttl_seconds = 60

def get_salary_schedule_for_district(
    table,
    district_id: str,
    year: Optional[str] = None
) -> List[Dict[str, Any]]:
    # Check cache
    cache_key = f"{district_id}#{year or 'all'}"
    if cache_key in _salary_cache:
        cached_data, timestamp = _salary_cache[cache_key]
        import time
        if time.time() - timestamp < _cache_ttl_seconds:
            return cached_data

    # ... rest of function with ProjectionExpression added

    # Cache result before returning
    import time
    _salary_cache[cache_key] = (result, time.time())
    return result
```

### Option B: Use Separate Optimized Module

**File:** `backend/routers/salary_public.py`

```python
# Line 11: Change import
from services.salary_service_optimized import (
    get_salary_schedule_for_district_optimized as get_salary_schedule_for_district,
    invalidate_salary_cache
)
```

**File:** `backend/routers/salary_admin.py`

```python
# After successful salary upload/apply
from services.salary_service_optimized import invalidate_salary_cache

# In apply_salary_data endpoint (after line XXX)
invalidate_salary_cache(district_id)
```

## Performance Benchmarks

### Before Optimization:
```
First request (cold):     1,200ms
Subsequent requests:      950ms
Average:                  1,000ms
```

### After Optimization (Projected):
```
First request (cold):     250ms  (ProjectionExpression + optimized code)
Cache hit:                50ms   (in-memory cache)
Cache miss:               200ms  (DynamoDB query + caching)
Average (50% hit rate):   125ms  (8x improvement)
```

### With DAX (Additional):
```
Cache hit:                5ms
Cache miss:               50ms
Average:                  10ms   (100x improvement, but $180/month cost)
```

## Monitoring & Validation

### Add Logging:
```python
import time

start = time.time()
result = get_salary_schedule_for_district(table, district_id, year)
duration = time.time() - start

logger.info(f"get_salary_schedule_for_district: {district_id}, "
            f"year={year}, records={len(result)}, duration={duration:.3f}s, "
            f"cache_hit={cache_hit}")
```

### CloudWatch Metrics to Track:
- `SalaryQueryDuration` - How long queries take
- `SalaryCacheHitRate` - % of requests served from cache
- `SalaryRecordsReturned` - Dataset size

## Trade-offs

| Strategy | Performance | Cost | Complexity | Invalidation |
|----------|-------------|------|------------|--------------|
| No cache | Baseline | Low | Simple | N/A |
| Lambda cache | 8x faster | $0 | Low | Manual |
| DAX | 100x faster | $180/mo | Medium | Automatic |
| Global Tables | Same | 2x storage | High | Automatic |

## Recommended Approach

**For current scale (< 1000 req/min):**
1. ✅ Use Lambda container caching (free, 8x improvement)
2. ✅ Add ProjectionExpression (reduces bandwidth)
3. ✅ Optimize dict operations (5% gains)

**Total cost:** $0
**Total effort:** 30 minutes
**Expected improvement:** ~1000ms → ~125ms (avg)

**When to upgrade to DAX:**
- Traffic exceeds 1000 requests/min
- Budget allows $180/month for caching
- Require <10ms response times

## Cache Warming Strategy (Optional)

For frequently accessed districts, pre-warm the cache on Lambda startup:

```python
# backend/main.py
POPULAR_DISTRICTS = ['district-123', 'district-456', 'district-789']

@app.on_event("startup")
async def warmup_cache():
    """Pre-load cache for popular districts"""
    import asyncio
    from services.salary_service_optimized import get_salary_schedule_for_district_optimized

    async def prefetch(district_id):
        try:
            get_salary_schedule_for_district_optimized(main_table, district_id)
        except Exception as e:
            logger.error(f"Cache warmup failed for {district_id}: {e}")

    await asyncio.gather(*[prefetch(d) for d in POPULAR_DISTRICTS])
    logger.info("Cache warmed up for popular districts")
```

## Next Steps

1. Review the optimized code in `backend/services/salary_service_optimized.py`
2. Choose Option A (drop-in replacement) or Option B (separate module)
3. Test with a sample district to verify performance improvement
4. Deploy and monitor CloudWatch logs for cache hit rates
5. Adjust TTL based on data update frequency

## Questions?

- **Q: Will cache cause stale data?**
  A: Yes, for up to 60 seconds. Call `invalidate_salary_cache(district_id)` after uploads.

- **Q: How much memory does the cache use?**
  A: ~1MB per district (5 years of data). Lambda has 512MB-3GB available.

- **Q: Does cache persist across Lambda instances?**
  A: No. Each Lambda container has its own cache. DAX provides shared cache.

- **Q: Can I disable caching for testing?**
  A: Yes, set `use_cache=False` or set environment variable `DISABLE_SALARY_CACHE=true`.
