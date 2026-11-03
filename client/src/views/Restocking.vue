<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else-if="placedOrder" class="card success-panel">
      <h3 class="success-title">{{ t('restocking.success.title') }}</h3>
      <dl class="success-details">
        <div>
          <dt>{{ t('restocking.success.orderNumber') }}</dt>
          <dd>{{ placedOrder.order_number }}</dd>
        </div>
        <div>
          <dt>{{ t('restocking.success.total') }}</dt>
          <dd>{{ money(placedOrder.total_cost) }}</dd>
        </div>
        <div>
          <dt>{{ t('restocking.success.leadTime') }}</dt>
          <dd>{{ t('restocking.days', { count: placedOrder.lead_time_days }) }}</dd>
        </div>
        <div>
          <dt>{{ t('restocking.success.expectedDelivery') }}</dt>
          <dd>{{ formatDate(placedOrder.expected_delivery) }}</dd>
        </div>
      </dl>
      <div class="success-actions">
        <router-link to="/orders" class="link-button">{{ t('restocking.success.viewOrders') }}</router-link>
        <button type="button" class="secondary-button" @click="placedOrder = null">
          {{ t('restocking.success.newOrder') }}
        </button>
      </div>
    </div>
    <div v-else>
      <div class="card budget-card">
        <div class="budget-top">
          <label class="budget-label" for="budget-slider">{{ t('restocking.budget') }}</label>
          <span class="budget-value">{{ money(budget) }}</span>
        </div>
        <input
          id="budget-slider"
          class="budget-slider"
          type="range"
          min="0"
          :max="maxBudget"
          :step="budgetStep"
          :value="budget"
          :aria-label="t('restocking.budgetSlider')"
          @input="onBudgetInput($event.target.value)"
        />
        <div class="budget-scale">
          <span>{{ money(0) }}</span>
          <span>{{ money(maxBudget) }}</span>
        </div>
        <div class="budget-summary">
          <div>
            <div class="summary-label">{{ t('restocking.selectedCost') }}</div>
            <div class="summary-value">{{ money(totalCost) }}</div>
          </div>
          <div>
            <div class="summary-label">{{ t('restocking.remainingBudget') }}</div>
            <div :class="['summary-value', { negative: remaining < 0 }]">{{ money(remaining) }}</div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.title') }}</h3>
        </div>
        <div v-if="lines.length === 0" class="empty-state">{{ t('restocking.noForecasts') }}</div>
        <div v-else class="table-container">
          <table class="restocking-table">
            <thead>
              <tr>
                <th class="col-include">{{ t('restocking.table.include') }}</th>
                <th>{{ t('restocking.table.item') }}</th>
                <th>{{ t('restocking.table.supplier') }}</th>
                <th>{{ t('restocking.table.trend') }}</th>
                <th>{{ t('restocking.table.demand') }}</th>
                <th class="num">{{ t('restocking.table.unitCost') }}</th>
                <th class="col-qty">{{ t('restocking.table.quantity') }}</th>
                <th class="num">{{ t('restocking.table.lineTotal') }}</th>
                <th class="num">{{ t('restocking.table.leadTime') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="line in lines" :key="line.sku" :class="{ excluded: !line.selected }">
                <td class="col-include">
                  <input
                    type="checkbox"
                    v-model="line.selected"
                    :aria-label="t('restocking.includeItem', { sku: line.sku })"
                  />
                </td>
                <td>
                  <strong>{{ line.sku }}</strong>
                  <div class="item-sub">{{ line.forecast.item_name }}</div>
                </td>
                <td>{{ line.forecast.supplier }}</td>
                <td>
                  <span :class="['badge', line.forecast.trend]">
                    {{ t(`trends.${line.forecast.trend}`) }}
                  </span>
                </td>
                <td>{{ line.forecast.current_demand }} &rarr; <strong>{{ line.forecast.forecasted_demand }}</strong></td>
                <td class="num">{{ money(line.forecast.unit_cost, 2) }}</td>
                <td class="col-qty">
                  <input
                    class="qty-input"
                    type="number"
                    min="1"
                    step="1"
                    v-model.number="line.quantity"
                    @change="normalizeQuantity(line)"
                  />
                </td>
                <td class="num">
                  <strong>{{ line.selected ? money(lineTotal(line)) : '-' }}</strong>
                </td>
                <td class="num">{{ line.forecast.lead_time_days }}</td>
              </tr>
            </tbody>
            <tfoot>
              <tr>
                <td colspan="7" class="foot-label">{{ t('restocking.totalCost') }}</td>
                <td class="num"><strong>{{ money(totalCost) }}</strong></td>
                <td></td>
              </tr>
              <tr>
                <td colspan="7" class="foot-label">{{ t('restocking.remainingBudget') }}</td>
                <td :class="['num', { negative: remaining < 0 }]"><strong>{{ money(remaining) }}</strong></td>
                <td></td>
              </tr>
              <tr>
                <td colspan="7" class="foot-label">{{ t('restocking.orderLeadTime') }}</td>
                <td class="num"><strong>{{ t('restocking.days', { count: orderLeadTime }) }}</strong></td>
                <td></td>
              </tr>
            </tfoot>
          </table>
        </div>

        <div class="order-actions">
          <div v-if="submitError" class="error inline-error">{{ submitError }}</div>
          <div v-else-if="remaining < 0" class="error inline-error">{{ t('restocking.overBudget') }}</div>
          <button type="button" class="place-order" :disabled="!canSubmit" @click="placeOrder">
            {{ submitting ? t('restocking.placing') : t('restocking.placeOrder') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'
import { formatCurrencyWithDecimals } from '../utils/currency'

// Trend priority: 'increasing' items are always ranked ahead of everything else.
const gapOf = (f) => f.forecasted_demand - f.current_demand

/**
 * Pure recommendation. Returns a Map of sku -> quantity for items to include.
 *
 * Only forecasts with a positive gap (forecasted - current) are candidates.
 * They are ranked 'increasing' trend first, then by relative gap
 * (forecasted - current) / current descending. We walk the ranked list with a
 * running remaining budget: the default quantity is the full gap; if the full
 * gap does not fit we take the largest affordable whole-unit quantity
 * (floor(remaining / unit_cost)) when that is at least 1. An item that cannot
 * afford even one unit is skipped, and we keep walking because later items
 * may be cheaper.
 */
function recommend(ranked, budget) {
  const result = new Map()
  let remaining = budget
  for (const f of ranked) {
    const gap = gapOf(f)
    if (!(f.unit_cost > 0)) continue
    const affordable = Math.floor((remaining + 1e-9) / f.unit_cost)
    const qty = Math.min(gap, affordable)
    if (qty >= 1) {
      result.set(f.item_sku, qty)
      remaining -= qty * f.unit_cost
    }
  }
  return result
}

const rankForecasts = (forecasts) => {
  return forecasts
    .filter(f => gapOf(f) > 0)
    .sort((a, b) => {
      const incA = a.trend === 'increasing' ? 0 : 1
      const incB = b.trend === 'increasing' ? 0 : 1
      if (incA !== incB) return incA - incB
      // Guard against current_demand of 0 (division by zero)
      const relA = a.current_demand > 0 ? gapOf(a) / a.current_demand : Infinity
      const relB = b.current_demand > 0 ? gapOf(b) / b.current_demand : Infinity
      return relB - relA
    })
}

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency, currentLocale } = useI18n()

    const loading = ref(true)
    const error = ref(null)
    const forecasts = ref([])
    const budget = ref(0)
    // Editable rows: { sku, forecast, selected, quantity }
    const lines = ref([])
    const submitting = ref(false)
    const submitError = ref(null)
    const placedOrder = ref(null)

    const money = (amount, decimals = 0) =>
      formatCurrencyWithDecimals(amount, currentCurrency.value, decimals)

    const formatDate = (value) => {
      const date = new Date(value)
      if (isNaN(date.getTime())) return value
      return date.toLocaleDateString(currentLocale.value === 'ja' ? 'ja-JP' : 'en-US', {
        year: 'numeric', month: 'short', day: 'numeric'
      })
    }

    const ranked = computed(() => rankForecasts([...forecasts.value]))

    // Cost to fully restock every gap, rounded up to a slider step.
    const budgetStep = computed(() => {
      const raw = ranked.value.reduce((s, f) => s + gapOf(f) * f.unit_cost, 0)
      return raw >= 10000 ? 1000 : raw >= 1000 ? 100 : 10
    })
    const maxBudget = computed(() => {
      const raw = ranked.value.reduce((s, f) => s + gapOf(f) * f.unit_cost, 0)
      return Math.max(budgetStep.value, Math.ceil(raw / budgetStep.value) * budgetStep.value)
    })

    // Rebuild rows from the recommendation. Items not recommended stay in the
    // table, unchecked, with their full gap as the default quantity.
    const regenerate = () => {
      const picks = recommend(ranked.value, budget.value)
      lines.value = ranked.value.map(f => ({
        sku: f.item_sku,
        forecast: f,
        selected: picks.has(f.item_sku),
        quantity: picks.get(f.item_sku) ?? gapOf(f)
      }))
    }

    const onBudgetInput = (value) => {
      budget.value = Number(value)
      // Moving the slider discards manual edits by design.
      regenerate()
    }

    // Quantity must be a whole number >= 1; fall back to 1 on bad input.
    const effectiveQty = (line) => {
      const q = Math.floor(Number(line.quantity))
      return Number.isFinite(q) && q >= 1 ? q : 1
    }
    const normalizeQuantity = (line) => {
      line.quantity = effectiveQty(line)
    }
    const lineTotal = (line) => effectiveQty(line) * line.forecast.unit_cost

    const selectedLines = computed(() => lines.value.filter(l => l.selected))
    const totalCost = computed(() => selectedLines.value.reduce((s, l) => s + lineTotal(l), 0))
    const remaining = computed(() => budget.value - totalCost.value)
    const orderLeadTime = computed(() =>
      selectedLines.value.reduce((m, l) => Math.max(m, l.forecast.lead_time_days), 0)
    )

    // Small epsilon avoids float noise rejecting an exactly-on-budget order.
    const canSubmit = computed(() =>
      !submitting.value &&
      selectedLines.value.length > 0 &&
      totalCost.value > 0 &&
      totalCost.value <= budget.value + 1e-9
    )

    const placeOrder = async () => {
      if (!canSubmit.value) return
      submitting.value = true
      submitError.value = null
      try {
        placedOrder.value = await api.createRestockingOrder({
          budget: budget.value,
          items: selectedLines.value.map(l => ({ item_sku: l.sku, quantity: effectiveQty(l) }))
        })
      } catch (err) {
        submitError.value = err.response?.data?.detail || t('restocking.orderFailed')
        console.error('Order error:', err)
      } finally {
        submitting.value = false
      }
    }

    const load = async () => {
      try {
        loading.value = true
        error.value = null
        forecasts.value = await api.getDemandForecasts()
        // Start at half of the full-restock budget so the recommendation is visible.
        budget.value = Math.round(maxBudget.value / 2 / budgetStep.value) * budgetStep.value
        regenerate()
      } catch (err) {
        error.value = t('restocking.loadFailed') + err.message
      } finally {
        loading.value = false
      }
    }

    onMounted(load)

    return {
      t,
      loading,
      error,
      budget,
      maxBudget,
      budgetStep,
      lines,
      totalCost,
      remaining,
      orderLeadTime,
      canSubmit,
      submitting,
      submitError,
      placedOrder,
      money,
      formatDate,
      onBudgetInput,
      normalizeQuantity,
      lineTotal,
      placeOrder
    }
  }
}
</script>

<style scoped>
.budget-card {
  padding: 1.5rem;
  margin-bottom: 1.5rem;
}

.budget-top {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 0.75rem;
}

.budget-label {
  font-size: 0.875rem;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.budget-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: #0f172a;
}

.budget-slider {
  width: 100%;
  accent-color: #0f172a;
}

.budget-scale {
  display: flex;
  justify-content: space-between;
  font-size: 0.813rem;
  color: #64748b;
}

.budget-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1.5rem;
  margin-top: 1.25rem;
  padding-top: 1rem;
  border-top: 1px solid #e2e8f0;
}

.summary-label {
  font-size: 0.813rem;
  color: #64748b;
}

.summary-value {
  font-size: 1.25rem;
  font-weight: 700;
  color: #0f172a;
}

.negative {
  color: #dc2626;
}

.restocking-table .num {
  text-align: right;
  white-space: nowrap;
}

.col-include {
  width: 70px;
  text-align: center;
}

.col-qty {
  width: 110px;
}

.qty-input {
  width: 90px;
  padding: 0.375rem 0.5rem;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  color: #0f172a;
}

.item-sub {
  font-size: 0.813rem;
  color: #64748b;
}

tr.excluded td {
  color: #94a3b8;
}

tr.excluded .item-sub {
  color: #94a3b8;
}

.restocking-table tfoot td {
  border-top: 1px solid #e2e8f0;
  background: #f8fafc;
}

.foot-label {
  text-align: right;
  color: #64748b;
  font-weight: 600;
}

.empty-state {
  padding: 1.5rem;
  color: #64748b;
}

.order-actions {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 1rem;
  padding: 1rem 1.5rem;
}

.inline-error {
  margin: 0;
  padding: 0.5rem 0.75rem;
}

.place-order,
.secondary-button,
.link-button {
  padding: 0.625rem 1.25rem;
  border-radius: 6px;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  text-decoration: none;
}

.place-order,
.link-button {
  background: #0f172a;
  color: white;
  border: 1px solid #0f172a;
}

.place-order:disabled {
  background: #cbd5e1;
  border-color: #cbd5e1;
  cursor: not-allowed;
}

.secondary-button {
  background: white;
  color: #0f172a;
  border: 1px solid #e2e8f0;
}

.success-panel {
  padding: 1.5rem;
}

.success-title {
  margin: 0 0 1rem;
  color: #059669;
}

.success-details {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 1rem;
  margin: 0 0 1.5rem;
}

.success-details dt {
  font-size: 0.813rem;
  color: #64748b;
}

.success-details dd {
  margin: 0.25rem 0 0;
  font-size: 1.125rem;
  font-weight: 700;
  color: #0f172a;
}

.success-actions {
  display: flex;
  gap: 0.75rem;
}
</style>
