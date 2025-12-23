<script setup>
defineProps({
  size: {
    type: String,
    default: 'md', // sm, md, lg
    validator: (v) => ['sm', 'md', 'lg'].includes(v)
  },
  showText: {
    type: Boolean,
    default: true
  }
})

const sizeClasses = {
  sm: { icon: 'w-6 h-6', text: 'text-lg' },
  md: { icon: 'w-8 h-8', text: 'text-xl' },
  lg: { icon: 'w-12 h-12', text: 'text-3xl' }
}
</script>

<template>
  <div class="flex items-center gap-2">
    <!-- Logo SVG inline -->
    <svg
      :class="sizeClasses[size].icon"
      viewBox="0 0 512 512"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <!-- Fond -->
      <rect x="16" y="16" width="480" height="480" rx="96" fill="url(#bgGrad)" />

      <!-- Connexions -->
      <g stroke="#475569" stroke-width="6" stroke-linecap="round" opacity="0.8">
        <line x1="256" y1="256" x2="128" y2="128" />
        <line x1="256" y1="256" x2="384" y2="128" />
        <line x1="256" y1="256" x2="128" y2="384" />
        <line x1="256" y1="256" x2="384" y2="384" />
        <line x1="128" y1="128" x2="384" y2="128" stroke-dasharray="12,8" />
        <line x1="128" y1="384" x2="384" y2="384" stroke-dasharray="12,8" />
      </g>

      <!-- Nodes satellites -->
      <g>
        <rect x="88" y="88" width="80" height="80" rx="16" fill="url(#nodeGrad)" />
        <rect x="104" y="108" width="48" height="8" rx="2" fill="#93c5fd" />
        <rect x="104" y="124" width="32" height="8" rx="2" fill="#93c5fd" opacity="0.6" />

        <rect x="344" y="88" width="80" height="80" rx="16" fill="url(#nodeGrad)" />
        <rect x="360" y="108" width="48" height="8" rx="2" fill="#93c5fd" />
        <rect x="360" y="124" width="32" height="8" rx="2" fill="#93c5fd" opacity="0.6" />

        <rect x="88" y="344" width="80" height="80" rx="16" fill="url(#nodeGrad)" />
        <rect x="104" y="364" width="48" height="8" rx="2" fill="#93c5fd" />
        <rect x="104" y="380" width="32" height="8" rx="2" fill="#93c5fd" opacity="0.6" />

        <rect x="344" y="344" width="80" height="80" rx="16" fill="url(#nodeGrad)" />
        <rect x="360" y="364" width="48" height="8" rx="2" fill="#93c5fd" />
        <rect x="360" y="380" width="32" height="8" rx="2" fill="#93c5fd" opacity="0.6" />
      </g>

      <!-- Node central -->
      <g>
        <circle cx="256" cy="256" r="56" fill="url(#centerGrad)" />
        <circle cx="256" cy="240" r="12" fill="white" opacity="0.9" />
        <circle cx="240" cy="268" r="8" fill="white" opacity="0.7" />
        <circle cx="272" cy="268" r="8" fill="white" opacity="0.7" />
        <line x1="256" y1="252" x2="244" y2="262" stroke="white" stroke-width="3" opacity="0.8" />
        <line x1="256" y1="252" x2="268" y2="262" stroke="white" stroke-width="3" opacity="0.8" />
      </g>

      <!-- Gradients -->
      <defs>
        <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" style="stop-color:#1e3a5f" />
          <stop offset="100%" style="stop-color:#0f172a" />
        </linearGradient>
        <linearGradient id="nodeGrad" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" style="stop-color:#3b82f6" />
          <stop offset="100%" style="stop-color:#1d4ed8" />
        </linearGradient>
        <linearGradient id="centerGrad" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" style="stop-color:#22c55e" />
          <stop offset="100%" style="stop-color:#15803d" />
        </linearGradient>
      </defs>
    </svg>

    <!-- Texte -->
    <span
      v-if="showText"
      :class="[sizeClasses[size].text, 'font-bold text-white']"
    >
      Infra-Mapper
    </span>
  </div>
</template>
