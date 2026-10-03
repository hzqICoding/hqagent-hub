// Browser-only verification fixture. Not referenced by the application or production entry.
import { createApp, h } from 'vue'
import HqInput from '@/shared/ui/HqInput.vue'
import HqTextarea from '@/shared/ui/HqTextarea.vue'
import HqSelect from '@/shared/ui/HqSelect.vue'
import HqCombobox from '@/shared/ui/HqCombobox.vue'
import HqCheckbox from '@/shared/ui/HqCheckbox.vue'
import HqRadioGroup from '@/shared/ui/HqRadioGroup.vue'
import HqSwitch from '@/shared/ui/HqSwitch.vue'

export function mountFormContrastFixture(host: HTMLElement) {
  const options = [{ value: 'example', label: '示例选项' }]
  const children = ['normal', 'disabled', 'readonly', 'empty', 'error'].flatMap((state) => {
    const value = state === 'empty' ? '' : '主题对比度示例'
    return [
      h('div', { 'data-probe': `HqInput-${state}` }, [h(HqInput, { modelValue: value, disabled: state === 'disabled', readonly: state === 'readonly', error: state === 'error', placeholder: '共享输入占位符' })]),
      h('div', { 'data-probe': `HqTextarea-${state}` }, [h(HqTextarea, { modelValue: value, disabled: state === 'disabled', readonly: state === 'readonly', error: state === 'error', placeholder: '多行输入占位符' })]),
      ...[HqSelect, HqCombobox].map((component, index) => h('div', { 'data-probe': `${index ? 'HqCombobox' : 'HqSelect'}-${state}` }, [h(component, { modelValue: value ? 'example' : '', options, disabled: state === 'disabled', error: state === 'error', placeholder: '共享选择占位符' })])),
    ]
  })
  for (const type of ['text', 'password', 'email', 'search', 'number', 'url', 'tel', 'date', 'time', 'datetime-local', 'month', 'week']) {
    for (const disabled of [false, true]) children.push(h('input', { class: 'hq-form-control border p-2', 'data-probe': `native-${type}-${disabled}`, type, disabled, placeholder: '原生控件占位符' }))
  }
  children.push(h('textarea', { class: 'hq-form-control border p-2', 'data-probe': 'native-textarea', placeholder: '原生多行输入' }))
  children.push(h('select', { class: 'hq-form-control border p-2', 'data-probe': 'native-select' }, [h('option', '示例选项')]))
  for (const disabled of [false, true]) children.push(
    h(HqCheckbox, { disabled, label: '复选框文字', modelValue: true }),
    h(HqRadioGroup, { disabled, modelValue: 'example', options }),
    h(HqSwitch, { disabled, label: '开关文字', modelValue: true }),
  )
  const app = createApp({ render: () => h('div', { style: 'display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px;padding:24px;background:var(--color-bg-app)' }, children) })
  app.mount(host)
  return () => app.unmount()
}
