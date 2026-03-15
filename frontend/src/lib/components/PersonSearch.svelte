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
		onselect: (person: PersonResult) => void;
		onclear?: () => void;
	}

	let {
		placeholder = 'Search by name…',
		confidenceThreshold,
		selected = null,
		accentColor = 'blue',
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

	// ── Colour helpers ────────────────────────────────────
	const chipBg     = $derived(accentColor === 'emerald' ? 'bg-emerald-50 dark:bg-emerald-950/40 border-emerald-200 dark:border-emerald-800' : 'bg-blue-50 dark:bg-blue-950/40 border-blue-200 dark:border-blue-800');
	const avatarBg   = $derived(accentColor === 'emerald' ? 'bg-emerald-600' : 'bg-blue-600');
	const focusRing  = $derived(accentColor === 'emerald' ? 'focus:ring-emerald-500/20 focus:border-emerald-500' : 'focus:ring-blue-500/20 focus:border-blue-500');
</script>

{#if selected}
	<!-- Selected chip -->
	<div class="flex items-center gap-2 border rounded-lg px-3 py-2 {chipBg}">
		<div class="w-7 h-7 rounded-full {avatarBg} flex items-center justify-center text-white text-xs font-bold shrink-0">
			{selected.name.slice(0, 2).toUpperCase()}
		</div>
		<div class="min-w-0 flex-1">
			<p class="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{selected.name}</p>
			{#if latestOrg(selected)}
				<p class="text-xs text-gray-400 truncate">{latestOrg(selected)}</p>
			{/if}
		</div>
		{#if onclear}
			<button
				onclick={onclear}
				class="shrink-0 w-5 h-5 flex items-center justify-center rounded text-gray-400
				       hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950 transition-colors"
				aria-label="Clear selection"
			>
				<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/>
				</svg>
			</button>
		{/if}
	</div>
{:else}
	<!-- Search input -->
	<div class="relative">
		<svg class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none"
			fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
			<path stroke-linecap="round" stroke-linejoin="round"
				d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"/>
		</svg>
		<input
			type="text"
			{placeholder}
			bind:value={query}
			oninput={onInput}
			class="w-full pl-9 pr-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg text-sm
			       bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder-gray-400
			       focus:outline-none focus:ring-2 transition-colors {focusRing}"
		/>
	</div>

	<!-- Results -->
	{#if searching}
		<div class="space-y-2 mt-2">
			{#each Array(3) as _}
				<div class="h-12 bg-gray-100 dark:bg-gray-800 rounded-lg animate-pulse"></div>
			{/each}
		</div>
	{:else if error}
		<p class="text-sm text-red-500 mt-2">{error}</p>
	{:else if query && clusters.length === 0}
		<div class="mt-2 py-6 text-center">
			<p class="text-sm text-gray-400">No results for "{query}"</p>
		</div>
	{:else if clusters.length > 0}
		<ul class="mt-2 space-y-0.5">
			{#each clusters as cluster}
				<li>
					<button
						onclick={() => { onselect(cluster.primary); query = ''; rawResults = []; }}
						class="w-full text-left px-3 py-2.5 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800
						       transition-colors flex items-center gap-3"
					>
						<div class="w-8 h-8 rounded-full bg-gray-100 dark:bg-gray-800 flex items-center justify-center
						            text-xs font-semibold text-gray-600 dark:text-gray-300 shrink-0">
							{cluster.primary.name.slice(0, 2).toUpperCase()}
						</div>
						<div class="min-w-0 flex-1">
							<div class="flex items-center gap-1.5">
								<p class="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
									{cluster.primary.name}
								</p>
								{#if cluster.members.length > 1}
									<span class="shrink-0 text-xs font-medium text-blue-600 dark:text-blue-400
									             bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800
									             rounded-full px-1.5 py-0.5">
										+{cluster.members.length - 1}
									</span>
								{/if}
							</div>
							{#if latestOrg(cluster.primary)}
								<p class="text-xs text-gray-400 truncate mt-0.5">{latestOrg(cluster.primary)}</p>
							{/if}
						</div>
					</button>
				</li>
			{/each}
		</ul>
	{/if}
{/if}
