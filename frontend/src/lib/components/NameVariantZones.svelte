<script lang="ts">
	import type { NameVariant } from '$lib/api';

	interface Props {
		nameVariants: NameVariant[];
		/** Set of variant names currently active (included). */
		activeNames: Set<string>;
		confidenceThreshold: number;
		/** Colour theme for the "in" zone badge. */
		inColor?: 'blue' | 'emerald';
		/** Called when a variant is toggled in or out. */
		ontoggle: (name: string) => void;
	}

	let {
		nameVariants,
		activeNames,
		confidenceThreshold,
		inColor = 'blue',
		ontoggle
	}: Props = $props();

	// ── Derived lists ─────────────────────────────────────
	const inList  = $derived(nameVariants.filter(v =>  activeNames.has(v.name)));
	const outList = $derived(nameVariants.filter(v => !activeNames.has(v.name)));

	// ── Drag-drop state ───────────────────────────────────
	let draggingName = $state<string | null>(null);
	let draggingFrom = $state<'in' | 'out' | null>(null);
	let dragOverZone = $state<'in' | 'out' | null>(null);
	let dEnterIn  = $state(0);
	let dEnterOut = $state(0);

	function startDrag(e: DragEvent, name: string, from: 'in' | 'out') {
		draggingName = name; draggingFrom = from;
		e.dataTransfer?.setData('text/plain', name);
	}

	function onDragEnd() {
		draggingName = null; draggingFrom = null; dragOverZone = null;
		dEnterIn = 0; dEnterOut = 0;
	}

	function onDragEnter(zone: 'in' | 'out') {
		if (draggingFrom === zone) return;
		if (zone === 'in') { dEnterIn++;  dragOverZone = 'in'; }
		else               { dEnterOut++; dragOverZone = 'out'; }
	}

	function onDragLeave(zone: 'in' | 'out') {
		if (zone === 'in') {
			dEnterIn = Math.max(0, dEnterIn - 1);
			if (dEnterIn === 0 && dragOverZone === 'in') dragOverZone = null;
		} else {
			dEnterOut = Math.max(0, dEnterOut - 1);
			if (dEnterOut === 0 && dragOverZone === 'out') dragOverZone = null;
		}
	}

	function onDragOver(e: DragEvent, zone: 'in' | 'out') {
		if (draggingFrom !== zone) e.preventDefault();
	}

	function onDrop(e: DragEvent, zone: 'in' | 'out') {
		e.preventDefault();
		dragOverZone = null; dEnterIn = 0; dEnterOut = 0;
		if (draggingName && draggingFrom !== zone) ontoggle(draggingName);
		draggingName = null; draggingFrom = null;
	}

	// ── Colour helpers ────────────────────────────────────
	const inZoneActive   = $derived(inColor === 'emerald' ? 'border-emerald-400 bg-emerald-50 dark:bg-emerald-950/30' : 'border-blue-400 bg-blue-50 dark:bg-blue-950/30');
	const inLabelClass   = $derived(inColor === 'emerald' ? 'text-emerald-500 dark:text-emerald-400' : 'text-blue-500 dark:text-blue-400');
	const inBadgeHigh    = $derived(inColor === 'emerald' ? 'bg-emerald-600 text-white border-emerald-600 hover:bg-emerald-700' : 'bg-blue-600 text-white border-blue-600 hover:bg-blue-700');
	const outHoverBorder = $derived(inColor === 'emerald' ? 'hover:border-emerald-400 hover:text-emerald-600 dark:hover:text-emerald-400' : 'hover:border-blue-400 hover:text-blue-600 dark:hover:text-blue-400');
</script>

<div class="space-y-2">
	<!-- Zone: In timeline -->
	<div
		role="region"
		aria-label="Active name variants drop zone"
		ondragenter={() => onDragEnter('in')}
		ondragleave={() => onDragLeave('in')}
		ondragover={(e) => onDragOver(e, 'in')}
		ondrop={(e) => onDrop(e, 'in')}
		class="rounded-lg border-2 transition-colors p-2
		       {dragOverZone === 'in' ? inZoneActive : 'border-dashed border-gray-200 dark:border-gray-700'}"
	>
		<p class="text-[10px] font-semibold uppercase tracking-wide mb-1.5 select-none {inLabelClass}">
			In timeline
		</p>
		<div class="flex flex-wrap gap-1.5 min-h-[28px]">
			{#each inList as variant}
				{@const lowConf = variant.score < confidenceThreshold}
				<button
					draggable="true"
					ondragstart={(e) => startDrag(e, variant.name, 'in')}
					ondragend={onDragEnd}
					onclick={() => ontoggle(variant.name)}
					title="Click or drag to remove — score {variant.score}%"
					class="text-xs px-2.5 py-1 rounded-full border transition-all flex items-center gap-1.5
					       cursor-grab active:cursor-grabbing select-none
					       {lowConf
					         ? 'bg-amber-500 text-white border-amber-500 hover:bg-amber-600'
					         : inBadgeHigh}"
				>
					{variant.name}
					<span class="font-mono tabular-nums {lowConf ? 'text-amber-200' : 'opacity-70'}">
						{variant.score}%
					</span>
				</button>
			{/each}
			{#if inList.length === 0}
				<p class="text-xs text-gray-400 dark:text-gray-500 italic py-0.5">Drop variants here to include them</p>
			{/if}
		</div>
	</div>

	<!-- Zone: Not in timeline -->
	<div
		role="region"
		aria-label="Excluded name variants drop zone"
		ondragenter={() => onDragEnter('out')}
		ondragleave={() => onDragLeave('out')}
		ondragover={(e) => onDragOver(e, 'out')}
		ondrop={(e) => onDrop(e, 'out')}
		class="rounded-lg border-2 transition-colors p-2
		       {dragOverZone === 'out'
		         ? 'border-gray-400 bg-gray-100 dark:bg-gray-800'
		         : 'border-dashed border-gray-200 dark:border-gray-700'}"
	>
		<p class="text-[10px] font-semibold uppercase tracking-wide text-gray-400 mb-1.5 select-none">
			Not in timeline
		</p>
		<div class="flex flex-wrap gap-1.5 min-h-[28px]">
			{#each outList as variant}
				<button
					draggable="true"
					ondragstart={(e) => startDrag(e, variant.name, 'out')}
					ondragend={onDragEnd}
					onclick={() => ontoggle(variant.name)}
					title="Click or drag to add — score {variant.score}%"
					class="text-xs px-2.5 py-1 rounded-full border transition-all flex items-center gap-1.5
					       cursor-grab active:cursor-grabbing select-none
					       bg-white dark:bg-gray-900 text-gray-500 dark:text-gray-400
					       border-gray-300 dark:border-gray-600 {outHoverBorder}"
				>
					{variant.name}
					<span class="font-mono tabular-nums text-gray-400 dark:text-gray-500">
						{variant.score}%
					</span>
				</button>
			{/each}
			{#if outList.length === 0}
				<p class="text-xs text-gray-400 dark:text-gray-500 italic py-0.5">Drop variants here to exclude them</p>
			{/if}
		</div>
	</div>
</div>
