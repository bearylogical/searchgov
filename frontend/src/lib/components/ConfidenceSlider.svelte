<script lang="ts">
	interface Props {
		value: number;
		onchange?: (value: number) => void;
	}

	let { value = $bindable(95), onchange }: Props = $props();

	const label = $derived(
		value >= 95 ? 'Strict' : value >= 80 ? 'Moderate' : value >= 65 ? 'Relaxed' : 'Broad'
	);

	function handleInput(e: Event) {
		value = Number((e.target as HTMLInputElement).value);
		onchange?.(value);
	}
</script>

<div class="rounded-lg border border-gray-200 dark:border-gray-700 p-3 space-y-2">
	<div class="flex items-center justify-between">
		<span class="text-xs font-medium text-gray-500 dark:text-gray-400">
			Confidence threshold — {value}%
		</span>
		<span class="text-xs text-gray-400 dark:text-gray-500">{label}</span>
	</div>
	<input
		type="range" min="40" max="100" step="5"
		{value}
		oninput={handleInput}
		class="w-full h-1.5 rounded-full accent-blue-600 cursor-pointer"
	/>
	<p class="text-xs text-gray-400 dark:text-gray-500 leading-snug">
		Variants below this score land in "Not in timeline" by default.
		Also controls search grouping.
	</p>
</div>
