<script lang="ts">
	import { people } from '$lib/api';
	import type { PersonResult } from '$lib/api';
	import { clusterResults } from '$lib/fuzzy';
	import type { Cluster } from '$lib/fuzzy';

	interface Props {
		placeholder?: string;
		/** Controls search result clustering threshold. */
		confidenceThreshold: number;
		/** When set, shows the selected chip instead of the search input. */
		selected?: PersonResult | null;
		/** Accent colour used for the selected chip and focus ring. */
		accentColor?: 'blue' | 'emerald';
		/**
		 * When true the input is disabled and a "loading" hint is shown.
		 * Useful to block the other slot while the first slot's career data loads.
		 */
		disabled?: boolean;
		onselect: (person: PersonResult) => void;
		onclear?: () => void;
	}

	let {
		placeholder = 'Search by name…',
		confidenceThreshold,
		selected = null,
		accentColor = 'blue',
		disabled = false,
		onselect,
		onclear
	}: Props = $props();

	// ── Internal search state ─────────────────────────────
	let query      = $state('');
	let rawResults = $state<PersonResult[]>([]);
	let searching  = $state(false);
	let error      = $state('');
	let timer: ReturnType<typeof setTimeout>;

	const clusters = $derived<Cluster[]>(clusterResults(rawResults, confidenceThreshold));

	function onInput() {
		clearTimeout(timer);
		rawResults = []; error = '';
		if (!query.trim()) return;
		timer = setTimeout(runSearch, 300);
	}

	async function runSearch() {
		searching = true;
		try { rawResults = await people.search(query); }
		catch (err: unknown) { error = err instanceof Error ? err.message : 'Search failed'; }
		finally { searching = false; }
	}

	// ── Helpers ───────────────────────────────────────────
	function latestOrg(person: PersonResult): string | null {
		const profile = person.employment_profile;
		if (!profile?.length) return null;
		const sorted = [...profile].sort((a, b) => {
			if (!a.start_date) return 1; if (!b.start_date) return -1;
			return b.start_date.localeCompare(a.start_date);
		});
		return sorted[0].org_name ?? sorted[0].entity_name ?? null;
	}

	// Palantir: blue → Blueprint blue, emerald → Blueprint green
	const accentColorVal = $derived(accentColor === 'emerald' ? 'var(--pt-green)' : 'var(--pt-blue)');
	const accentTint     = $derived(accentColor === 'emerald' ? 'var(--pt-green-tint)' : 'var(--pt-blue-tint)');
	const accentBorder   = $derived(accentColor === 'emerald' ? 'rgba(13, 128, 80, 0.4)' : 'rgba(19, 124, 189, 0.4)');
</script>

{#if selected}
	<!-- Selected chip — Palantir flat style -->
	<div class="flex items-center gap-2 px-3 py-2"
	     style="background: {accentTint}; border: 1px solid {accentBorder}; border-radius: 2px;">
		<div class="w-7 h-7 flex items-center justify-center text-white text-xs font-bold shrink-0"
		     style="background: {accentColorVal}; border-radius: 2px; font-family: var(--font-mono);">
			{selected.name.slice(0, 2).toUpperCase()}
		</div>
		<div class="min-w-0 flex-1">
			<p class="text-xs font-medium truncate" style="color: var(--pt-text-primary);">{selected.name}</p>
			{#if latestOrg(selected)}
				<p class="text-xs truncate mt-0.5" style="color: var(--pt-text-muted);">{latestOrg(selected)}</p>
			{/if}
		</div>
		{#if onclear}
			<button
				onclick={onclear}
				class="shrink-0 w-6 h-6 flex items-center justify-center transition-colors"
				style="color: var(--pt-text-muted); border-radius: 2px;"
				onmouseover={(e) => { (e.currentTarget as HTMLElement).style.color = 'var(--pt-red)'; (e.currentTarget as HTMLElement).style.background = 'var(--pt-red-tint)'; }}
				onmouseout={(e) => { (e.currentTarget as HTMLElement).style.color = 'var(--pt-text-muted)'; (e.currentTarget as HTMLElement).style.background = ''; }}
				aria-label="Clear selection"
			>
				<svg class="w-3 h-3" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/>
				</svg>
			</button>
		{/if}
	</div>
{:else}
	<!-- Search input — touch-friendly height (min 44px touch target) -->
	<div class="relative">
		{#if disabled}
			<!-- Loading spinner while the other slot's career is resolving -->
			<div class="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5">
				<svg class="animate-spin w-3.5 h-3.5" style="color: var(--pt-text-muted);"
				     fill="none" viewBox="0 0 24 24">
					<circle class="opacity-25" cx="12" cy="12" r="10"
					        stroke="currentColor" stroke-width="3"/>
					<path class="opacity-75" fill="currentColor"
					      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
				</svg>
			</div>
		{:else}
			<svg class="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 pointer-events-none"
			     style="color: var(--pt-text-muted);"
			     fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round"
				      d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"/>
			</svg>
		{/if}
		<input
			type="text"
			placeholder={disabled ? 'Waiting for career data…' : placeholder}
			bind:value={query}
			oninput={disabled ? undefined : onInput}
			disabled={disabled}
			class="pt-input"
			style="padding-left: 2rem; min-height: 40px; {disabled ? 'opacity: 0.45; cursor: not-allowed; pointer-events: none;' : ''}"
		/>
	</div>

	<!-- Results -->
	{#if searching}
		<div class="space-y-1.5 mt-2">
			{#each Array(3) as _}
				<div class="h-11 rounded animate-pulse" style="background: var(--pt-bg-2);"></div>
			{/each}
		</div>
	{:else if error}
		<p class="text-xs mt-2" style="color: var(--pt-red);">{error}</p>
	{:else if query && clusters.length === 0}
		<div class="mt-2 py-5 text-center">
			<p class="text-xs" style="color: var(--pt-text-muted);">No results for "{query}"</p>
		</div>
	{:else if clusters.length > 0}
		<ul class="mt-1.5 space-y-0.5">
			{#each clusters as cluster}
				<li>
					<!-- Touch-friendly: min 44px height -->
					<button
						onclick={() => { onselect(cluster.primary); query = ''; rawResults = []; }}
						class="w-full text-left px-3 py-2.5 flex items-center gap-2.5 transition-colors"
						style="border-radius: 2px; min-height: 44px;"
						onmouseover={(e) => { (e.currentTarget as HTMLElement).style.background = 'var(--pt-bg-3)'; }}
						onmouseout={(e) => { (e.currentTarget as HTMLElement).style.background = ''; }}
					>
						<div class="w-7 h-7 flex items-center justify-center text-xs font-semibold shrink-0"
						     style="background: var(--pt-bg-3); color: var(--pt-text-secondary); border-radius: 2px; font-family: var(--font-mono);">
							{cluster.primary.name.slice(0, 2).toUpperCase()}
						</div>
						<div class="min-w-0 flex-1">
							<div class="flex items-center gap-1.5">
								<p class="text-xs font-medium truncate" style="color: var(--pt-text-primary);">
									{cluster.primary.name}
								</p>
								{#if cluster.members.length > 1}
									<span class="shrink-0 pt-tag pt-tag-blue">+{cluster.members.length - 1}</span>
								{/if}
							</div>
							{#if latestOrg(cluster.primary)}
								<p class="text-xs truncate mt-0.5" style="color: var(--pt-text-muted);">{latestOrg(cluster.primary)}</p>
							{/if}
						</div>
					</button>
				</li>
			{/each}
		</ul>
	{/if}
{/if}
