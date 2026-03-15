<script lang="ts">
	import { organisations } from '$lib/api';
	import type { OrgResult } from '$lib/api';
	import { isAuthenticated, authReady } from '$lib/auth';
	import { goto } from '$app/navigation';

	$effect(() => {
		if ($authReady && !$isAuthenticated) goto('/login?redirect=/organisation');
	});

	let query = $state('');
	let results = $state<OrgResult[]>([]);
	let selected = $state<OrgResult | null>(null);
	let tree = $state<OrgResult[]>([]);
	let timeline = $state<string[]>([]);
	let selectedDate = $state('');
	let searching = $state(false);
	let loadingTree = $state(false);
	let searchError = $state('');

	let searchTimeout: ReturnType<typeof setTimeout>;

	function onQueryInput() {
		clearTimeout(searchTimeout);
		selected = null;
		tree = [];
		timeline = [];
		if (!query.trim()) { results = []; return; }
		searchTimeout = setTimeout(runSearch, 300);
	}

	async function runSearch() {
		searching = true;
		searchError = '';
		try {
			results = await organisations.search(query);
		} catch (err: unknown) {
			searchError = err instanceof Error ? err.message : 'Search failed';
			results = [];
		} finally {
			searching = false;
		}
	}

	async function selectOrg(org: OrgResult) {
		selected = org;
		tree = [];
		timeline = [];
		selectedDate = '';
		loadingTree = true;
		try {
			[tree, timeline] = await Promise.all([
				organisations.tree(org.id),
				organisations.timeline(org.id)
			]);
			if (timeline.length > 0) selectedDate = timeline[timeline.length - 1];
		} finally {
			loadingTree = false;
		}
	}

	async function loadTreeAtDate() {
		if (!selected) return;
		loadingTree = true;
		try {
			tree = await organisations.tree(selected.id, selectedDate);
		} finally {
			loadingTree = false;
		}
	}

	function formatDate(d: string) {
		return new Date(d).toLocaleDateString('en-SG', { year: 'numeric', month: 'short' });
	}
</script>

<div class="flex-1 flex flex-col lg:flex-row overflow-hidden" style="height: calc(100vh - 3.5rem - 49px)">
	<!-- ── Left panel: search + results ───────────────── -->
	<aside class="w-full lg:w-80 xl:w-96 shrink-0 flex flex-col border-b lg:border-b-0 lg:border-r border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900">
		<!-- Search header -->
		<div class="p-4 border-b border-gray-100 dark:border-gray-800">
			<h1 class="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">Organisation Explorer</h1>
			<div class="relative">
				<svg
					class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 dark:text-gray-500 pointer-events-none"
					fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"
				>
					<path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"/>
				</svg>
				<input
					type="text"
					placeholder="Search by organisation…"
					bind:value={query}
					oninput={onQueryInput}
					class="w-full pl-9 pr-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg text-sm
					       bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 transition-colors
					       focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
				/>
			</div>
		</div>

		<!-- Results -->
		<div class="flex-1 overflow-y-auto">
			{#if searching}
				<div class="p-4 space-y-2">
					{#each Array(4) as _}
						<div class="h-12 bg-gray-100 dark:bg-gray-800 rounded-lg animate-pulse"></div>
					{/each}
				</div>
			{:else if searchError}
				<div class="p-4">
					<p class="text-sm text-red-600">{searchError}</p>
				</div>
			{:else if query && results.length === 0}
				<div class="p-8 text-center">
					<svg class="w-8 h-8 text-gray-300 dark:text-gray-600 mx-auto mb-2" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" d="M15.75 15.75l-2.489-2.489m0 0a3.375 3.375 0 10-4.773-4.773 3.375 3.375 0 004.774 4.774zM21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
					</svg>
					<p class="text-sm text-gray-400 dark:text-gray-500">No results for "{query}"</p>
				</div>
			{:else if !query}
				<div class="p-8 text-center">
					<svg class="w-8 h-8 text-gray-200 dark:text-gray-700 mx-auto mb-2" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" d="M3.75 21h16.5M4.5 3h15M5.25 3v18m13.5-18v18M9 6.75h1.5m-1.5 3h1.5m-1.5 3h1.5m3-6H15m-1.5 3H15m-1.5 3H15M9 21v-3.375c0-.621.504-1.125 1.125-1.125h3.75c.621 0 1.125.504 1.125 1.125V21"/>
					</svg>
					<p class="text-sm text-gray-400 dark:text-gray-500">Search for an organisation to begin</p>
				</div>
			{:else}
				<ul>
					{#each results as org}
						<li>
							<button
								onclick={() => selectOrg(org)}
								class="w-full text-left px-4 py-3 hover:bg-gray-50 dark:bg-gray-950 transition-colors flex items-center gap-3
								       {selected?.id === org.id ? 'bg-blue-50 border-r-2 border-blue-500' : ''}"
							>
								<div class="w-8 h-8 rounded-lg bg-gray-100 dark:bg-gray-800 flex items-center justify-center shrink-0">
									<svg class="w-4 h-4 text-gray-500 dark:text-gray-400" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" d="M3.75 21h16.5M4.5 3h15M5.25 3v18m13.5-18v18M9 6.75h1.5m-1.5 3h1.5m-1.5 3h1.5m3-6H15m-1.5 3H15m-1.5 3H15M9 21v-3.375c0-.621.504-1.125 1.125-1.125h3.75c.621 0 1.125.504 1.125 1.125V21"/>
									</svg>
								</div>
								<div class="min-w-0">
									<p class="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{org.name}</p>
									{#if org.department}
										<p class="text-xs text-gray-400 dark:text-gray-500 truncate">{org.department}</p>
									{/if}
								</div>
							</button>
						</li>
					{/each}
				</ul>
			{/if}
		</div>
	</aside>

	<!-- ── Right panel: org tree ──────────────────────── -->
	<section class="flex-1 overflow-y-auto bg-gray-50 dark:bg-gray-950">
		{#if !selected}
			<div class="h-full flex items-center justify-center p-8">
				<div class="text-center">
					<svg class="w-12 h-12 text-gray-200 dark:text-gray-700 mx-auto mb-3" fill="none" stroke="currentColor" stroke-width="1" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" d="M2.25 21h19.5m-18-18v18m10.5-18v18m6-13.5V21M6.75 6.75h.75m-.75 3h.75m-.75 3h.75m3-6h.75m-.75 3h.75m-.75 3h.75M6.75 21v-3.375c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21M3 3h12m-.75 4.5H21m-3.75 3.75h.008v.008h-.008v-.008zm0 3h.008v.008h-.008v-.008zm0 3h.008v.008h-.008v-.008z"/>
					</svg>
					<p class="text-sm text-gray-400 dark:text-gray-500">Select an organisation to explore its hierarchy</p>
				</div>
			</div>
		{:else}
			<div class="max-w-2xl mx-auto p-6">
				<!-- Org header card -->
				<div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl p-5 shadow-sm mb-6">
					<div class="flex items-start gap-4">
						<div class="w-10 h-10 rounded-lg bg-violet-600 flex items-center justify-center shrink-0">
							<svg class="w-5 h-5 text-white" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" d="M3.75 21h16.5M4.5 3h15M5.25 3v18m13.5-18v18M9 6.75h1.5m-1.5 3h1.5m-1.5 3h1.5m3-6H15m-1.5 3H15m-1.5 3H15M9 21v-3.375c0-.621.504-1.125 1.125-1.125h3.75c.621 0 1.125.504 1.125 1.125V21"/>
							</svg>
						</div>
						<div class="min-w-0 flex-1">
							<h2 class="text-base font-semibold text-gray-900 dark:text-gray-100">{selected.name}</h2>
							{#if selected.department}
								<p class="text-sm text-gray-500 dark:text-gray-400 mt-0.5">{selected.department}</p>
							{/if}
							{#if !loadingTree && tree.length > 0}
								<p class="text-xs text-gray-400 dark:text-gray-500 mt-1">{tree.length} sub-organisation{tree.length !== 1 ? 's' : ''}</p>
							{/if}
						</div>
					</div>

					<!-- Timeline date picker -->
					{#if timeline.length > 0}
						<div class="mt-4 pt-4 border-t border-gray-100 dark:border-gray-800 flex items-center gap-3 flex-wrap">
							<span class="text-xs font-medium text-gray-500 dark:text-gray-400">View at snapshot:</span>
							<div class="flex flex-wrap gap-1.5">
								{#each timeline as d}
									<button
										onclick={() => { selectedDate = d; loadTreeAtDate(); }}
										class="text-xs px-2.5 py-1 rounded-full border transition-colors
										       {selectedDate === d
										         ? 'bg-blue-600 text-white border-blue-600'
										         : 'bg-white dark:bg-gray-900 text-gray-600 dark:text-gray-300 border-gray-300 dark:border-gray-700 hover:border-blue-400 hover:text-blue-600'}"
									>
										{formatDate(d)}
									</button>
								{/each}
							</div>
						</div>
					{/if}
				</div>

				<!-- Sub-org tree -->
				{#if loadingTree}
					<div class="space-y-2">
						{#each Array(6) as _}
							<div class="h-14 bg-gray-100 dark:bg-gray-800 rounded-xl animate-pulse"></div>
						{/each}
					</div>
				{:else if tree.length === 0}
					<div class="text-center py-12">
						<svg class="w-8 h-8 text-gray-200 dark:text-gray-700 mx-auto mb-2" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" d="M2.25 12l8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25"/>
						</svg>
						<p class="text-sm text-gray-400 dark:text-gray-500">No sub-organisations found.</p>
					</div>
				{:else}
					<ul class="space-y-2">
						{#each tree as child}
							<li class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl px-4 py-3.5 shadow-sm hover:shadow-md transition-shadow flex items-center gap-3">
								<div class="w-1 h-8 rounded-full bg-violet-200 dark:bg-violet-800 shrink-0"></div>
								<div class="min-w-0">
									<p class="text-sm font-medium text-gray-900 dark:text-gray-100">{child.name}</p>
									{#if child.department}
										<p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{child.department}</p>
									{/if}
								</div>
							</li>
						{/each}
					</ul>
				{/if}
			</div>
		{/if}
	</section>
</div>
