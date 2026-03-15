<script lang="ts">
	interface Props {
		/** Tooltip text to display on hover */
		tip: string;
		/** Optional additional class for positioning */
		class?: string;
	}

	let { tip, class: cls = '' }: Props = $props();

	let visible = $state(false);
	let btnEl = $state<HTMLButtonElement | undefined>();
	let tipX = $state(0);
	let tipY = $state(0);

	function showTip() {
		if (btnEl) {
			const r = btnEl.getBoundingClientRect();
			tipX = r.left + r.width / 2;
			tipY = r.top;
		}
		visible = true;
	}
</script>

<span class="relative inline-flex items-center {cls}">
	<button
		bind:this={btnEl}
		type="button"
		onmouseenter={showTip}
		onmouseleave={() => (visible = false)}
		onfocus={showTip}
		onblur={() => (visible = false)}
		aria-label="More information"
		class="w-4 h-4 rounded-full border border-gray-300 dark:border-gray-600
		       bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400
		       text-[10px] font-bold leading-none flex items-center justify-center
		       hover:border-blue-400 hover:text-blue-500 transition-colors focus:outline-none"
	>
		?
	</button>
</span>

{#if visible}
	<!-- Portal-style: fixed to viewport so never clipped by overflow:hidden ancestors -->
	<div
		role="tooltip"
		style="position: fixed; left: {tipX}px; top: calc({tipY}px - 0.375rem); transform: translate(-50%, -100%);"
		class="z-[9999] w-56 rounded-lg border border-gray-200 dark:border-gray-700
		       bg-white dark:bg-gray-900 shadow-lg px-3 py-2 pointer-events-none
		       text-xs text-gray-600 dark:text-gray-300 leading-snug"
	>
		{tip}
		<span class="absolute top-full left-1/2 -translate-x-1/2 -mt-px
		             border-4 border-transparent border-t-gray-200 dark:border-t-gray-700">
		</span>
	</div>
{/if}
