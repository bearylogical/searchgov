<script lang="ts">
	interface Props {
		/** Tooltip text to display on hover */
		tip: string;
		/** Optional additional class for positioning */
		class?: string;
	}

	let { tip, class: cls = '' }: Props = $props();

	let visible = $state(false);
</script>

<span class="relative inline-flex items-center {cls}">
	<button
		type="button"
		onmouseenter={() => (visible = true)}
		onmouseleave={() => (visible = false)}
		onfocus={() => (visible = true)}
		onblur={() => (visible = false)}
		aria-label="More information"
		class="w-4 h-4 rounded-full border border-gray-300 dark:border-gray-600
		       bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400
		       text-[10px] font-bold leading-none flex items-center justify-center
		       hover:border-blue-400 hover:text-blue-500 transition-colors focus:outline-none"
	>
		?
	</button>
	{#if visible}
		<div
			role="tooltip"
			class="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 z-50
			       w-56 rounded-lg border border-gray-200 dark:border-gray-700
			       bg-white dark:bg-gray-900 shadow-lg px-3 py-2
			       text-xs text-gray-600 dark:text-gray-300 leading-snug pointer-events-none"
		>
			{tip}
			<!-- Arrow -->
			<span class="absolute top-full left-1/2 -translate-x-1/2 -mt-px
			             border-4 border-transparent border-t-gray-200 dark:border-t-gray-700">
			</span>
		</div>
	{/if}
</span>
