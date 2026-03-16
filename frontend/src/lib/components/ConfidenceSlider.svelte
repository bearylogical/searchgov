<script lang="ts">
	interface Props {
		value: number;
		compact?: boolean;
		onchange?: (value: number) => void;
	}

	let { value = $bindable(95), compact = false, onchange }: Props = $props();

	const label = $derived(
		value >= 95 ? 'Strict' : value >= 80 ? 'Moderate' : value >= 65 ? 'Relaxed' : 'Broad'
	);

	function handleInput(e: Event) {
		value = Number((e.target as HTMLInputElement).value);
		onchange?.(value);
	}
</script>

<div class="p-3 space-y-2" style="border: 1px solid var(--pt-border-muted); border-radius: 2px; background: var(--pt-bg-0);">
	<div class="flex items-center justify-between">
		<span class="pt-label">Confidence — <span class="pt-data">{value}%</span></span>
		<span class="pt-tag pt-tag-blue">{label}</span>
	</div>
	<!-- Touch-friendly slider track -->
	<input
		type="range" min="40" max="100" step="5"
		{value}
		oninput={handleInput}
		class="w-full cursor-pointer"
		style="height: 20px; accent-color: var(--pt-blue);"
	/>
	{#if !compact}
		<p class="text-xs leading-snug" style="color: var(--pt-text-muted);">
			Variants below this score land in "Not in timeline" by default.
			Also controls search grouping.
		</p>
	{/if}
</div>
