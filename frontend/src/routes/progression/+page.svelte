<script lang="ts">
	import { people } from '$lib/api';
	import type { PersonResult, EmploymentEntry, NameVariant } from '$lib/api';
	import { isAuthenticated } from '$lib/auth';
	import { goto } from '$app/navigation';

	$effect(() => {
		if (!$isAuthenticated) goto('/login?redirect=/progression');
	});

	let query = $state('');
	let results = $state<PersonResult[]>([]);
	let selected = $state<PersonResult | null>(null);

	// Full original fetch — never mutated so reset is always possible
	let originalCareer = $state<EmploymentEntry[]>([]);
	// Working copy — entries can be removed individually
	let career = $state<EmploymentEntry[]>([]);
	// Name variants with similarity scores fetched from backend
	let nameVariants = $state<NameVariant[]>([]);
	// Which name variants are toggled on
	let activeNames = $state<Set<string>>(new Set());

	let searching = $state(false);
	let loadingCareer = $state(false);
	let searchError = $state('');

	let searchTimeout: ReturnType<typeof setTimeout>;

	function onQueryInput() {
		clearTimeout(searchTimeout);
		selected = null;
		career = [];
		originalCareer = [];
		nameVariants = [];
		activeNames = new Set();
		if (!query.trim()) { results = []; return; }
		searchTimeout = setTimeout(runSearch, 300);
	}

	async function runSearch() {
		searching = true;
		searchError = '';
		try {
			results = await people.search(query);
		} catch (err: unknown) {
			searchError = err instanceof Error ? err.message : 'Search failed';
			results = [];
		} finally {
			searching = false;
		}
	}

	async function selectPerson(person: PersonResult) {
		selected = person;
		career = [];
		originalCareer = [];
		nameVariants = [];
		activeNames = new Set();
		loadingCareer = true;
		try {
			// Fetch similar name variants (with scores) and full fuzzy career in parallel
			const [variants, raw] = await Promise.all([
				people.similarNames(person.name),
				people.careerByName(person.name, true)
			]);
			nameVariants = variants;
			const sorted = [...raw].sort((a, b) => {
				if (!a.start_date) return 1;
				if (!b.start_date) return -1;
				return a.start_date.localeCompare(b.start_date);
			});
			originalCareer = sorted;
			career = sorted;
			// All name variants active by default
			activeNames = new Set(variants.map(v => v.name));
		} finally {
			loadingCareer = false;
		}
	}

	// All unique name variants (from backend similarity search)
	const allNames = $derived(nameVariants.map(v => v.name));

	function toggleName(name: string) {
		const next = new Set(activeNames);
		if (next.has(name)) {
			next.delete(name);
		} else {
			next.add(name);
		}
		activeNames = next;
		// Rebuild career from originalCareer filtered by active names,
		// excluding any entries already manually removed
		const removedIds = new Set(
			originalCareer
				.filter(e => !career.some(c => c.id === e.id))
				.map(e => e.id)
		);
		career = originalCareer.filter(
			e => !removedIds.has(e.id) && (!e.person_name || next.has(e.person_name))
		);
	}

	function removeEntry(entry: EmploymentEntry) {
		career = career.filter(e => e !== entry);
	}

	function reset() {
		activeNames = new Set(nameVariants.map(v => v.name));
		career = [...originalCareer];
	}

	// Profile stats derived from current (filtered) career
	const employmentSpan = $derived(() => {
		const starts = career.map(e => e.start_date).filter(Boolean) as string[];
		const ends = career.map(e => e.end_date).filter(Boolean) as string[];
		return {
			from: starts.length ? formatDate(starts[0]) : null,
			to: career.some(e => !e.end_date) ? 'Present' : (ends.length ? formatDate(ends[ends.length - 1]) : null)
		};
	});

	const distinctOrgs = $derived(
		[...new Set(career.map(e => orgLabel(e)))]
	);

	const isDirty = $derived(
		career.length !== originalCareer.length || activeNames.size !== allNames.length
	);

	function formatDate(d: string | null) {
		if (!d) return 'Present';
		return new Date(d).toLocaleDateString('en-SG', { year: 'numeric', month: 'short' });
	}

	function formatDuration(days: number | null) {
		if (!days) return null;
		const months = Math.round(days / 30.44);
		if (months < 12) return `${months}mo`;
		const years = Math.floor(months / 12);
		const rem = months % 12;
		return rem > 0 ? `${years}y ${rem}mo` : `${years}y`;
	}

	function orgLabel(e: EmploymentEntry) {
		return e.org_name ?? e.entity_name ?? 'Unknown organisation';
	}

	function isActive(e: EmploymentEntry) {
		return !e.end_date;
	}

	function latestOrg(person: PersonResult): string | null {
		const profile = person.employment_profile;
		if (!profile?.length) return null;
		const sorted = [...profile].sort((a, b) => {
			if (!a.start_date) return 1;
			if (!b.start_date) return -1;
			return b.start_date.localeCompare(a.start_date);
		});
		return sorted[0].org_name ?? sorted[0].entity_name ?? null;
	}
</script>

<div class="flex-1 flex flex-col lg:flex-row overflow-hidden" style="height: calc(100vh - 3.5rem - 49px)">
	<!-- ── Left panel: search + results ───────────────── -->
	<aside class="w-full lg:w-80 xl:w-96 shrink-0 flex flex-col border-b lg:border-b-0 lg:border-r border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900">
		<div class="p-4 border-b border-gray-100 dark:border-gray-800">
			<h1 class="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">Career Progression</h1>
			<div class="relative">
				<svg class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 dark:text-gray-500 pointer-events-none"
					fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"/>
				</svg>
				<input
					type="text"
					placeholder="Search by name…"
					bind:value={query}
					oninput={onQueryInput}
					class="w-full pl-9 pr-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg text-sm
					       bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500
					       transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
				/>
			</div>
		</div>

		<div class="flex-1 overflow-y-auto">
			{#if searching}
				<div class="p-4 space-y-2">
					{#each Array(4) as _}
						<div class="h-16 bg-gray-100 dark:bg-gray-800 rounded-lg animate-pulse"></div>
					{/each}
				</div>
			{:else if searchError}
				<div class="p-4"><p class="text-sm text-red-600">{searchError}</p></div>
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
						<path stroke-linecap="round" stroke-linejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z"/>
					</svg>
					<p class="text-sm text-gray-400 dark:text-gray-500">Search for a person to begin</p>
				</div>
			{:else}
				<ul>
					{#each results as person}
						<li>
							<button
								onclick={() => selectPerson(person)}
								class="w-full text-left px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors
								       {selected?.id === person.id ? 'bg-blue-50 dark:bg-blue-950 border-r-2 border-blue-500' : ''}"
							>
								<div class="flex items-center gap-3">
									<div class="w-8 h-8 rounded-full bg-gray-100 dark:bg-gray-800 flex items-center justify-center shrink-0 text-xs font-semibold text-gray-600 dark:text-gray-300">
										{person.name.slice(0, 2).toUpperCase()}
									</div>
									<div class="min-w-0 flex-1">
										<p class="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{person.name}</p>
										{#if latestOrg(person)}
											<p class="text-xs text-gray-400 dark:text-gray-500 truncate mt-0.5">{latestOrg(person)}</p>
										{:else if person.email}
											<p class="text-xs text-gray-400 dark:text-gray-500 truncate mt-0.5">{person.email}</p>
										{/if}
									</div>
								</div>
							</button>
						</li>
					{/each}
				</ul>
			{/if}
		</div>
	</aside>

	<!-- ── Right panel ────────────────────────────────── -->
	<section class="flex-1 overflow-y-auto bg-gray-50 dark:bg-gray-950">
		{#if !selected}
			<div class="h-full flex items-center justify-center p-8">
				<div class="text-center">
					<svg class="w-12 h-12 text-gray-200 dark:text-gray-700 mx-auto mb-3" fill="none" stroke="currentColor" stroke-width="1" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z"/>
					</svg>
					<p class="text-sm text-gray-400 dark:text-gray-500">Select a person to view their career history</p>
				</div>
			</div>
		{:else}
			<div class="p-6 space-y-6">

				<!-- Profile header -->
				<div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl p-5 shadow-sm">
					<div class="flex items-center gap-4">
						<div class="w-12 h-12 rounded-full bg-blue-600 flex items-center justify-center text-white font-bold text-lg shrink-0">
							{selected.name.slice(0, 2).toUpperCase()}
						</div>
						<div class="min-w-0 flex-1">
							<h2 class="text-base font-semibold text-gray-900 dark:text-gray-100">{selected.name}</h2>
							{#if selected.email}
								<p class="text-sm text-gray-500 dark:text-gray-400 truncate">{selected.email}</p>
							{/if}
							{#if selected.tel}
								<p class="text-xs text-gray-400 dark:text-gray-500">{selected.tel}</p>
							{/if}
						</div>
						{#if !loadingCareer && career.length > 0}
							<div class="shrink-0 text-right">
								<p class="text-lg font-bold text-gray-900 dark:text-gray-100">{career.length}</p>
								<p class="text-xs text-gray-400 dark:text-gray-500">
									{career.length !== originalCareer.length ? `of ${originalCareer.length} ` : ''}roles
								</p>
							</div>
						{/if}
					</div>

					<!-- Name variant toggles -->
					{#if !loadingCareer && nameVariants.length > 0}
						<div class="mt-4 pt-4 border-t border-gray-100 dark:border-gray-800">
							<div class="flex items-center justify-between mb-2">
								<p class="text-xs font-medium text-gray-500 dark:text-gray-400">
									{nameVariants.length > 1 ? 'Name variants — click to include / exclude' : 'Matched name'}
								</p>
								{#if isDirty}
									<button
										onclick={reset}
										class="text-xs text-blue-600 dark:text-blue-400 hover:underline"
									>
										Reset
									</button>
								{/if}
							</div>
							<div class="flex flex-wrap gap-1.5">
								{#each nameVariants as variant}
									<button
										onclick={() => toggleName(variant.name)}
										title="Similarity score: {variant.score}%"
										class="text-xs px-2.5 py-1 rounded-full border transition-colors flex items-center gap-1.5
										       {activeNames.has(variant.name)
										         ? 'bg-blue-600 text-white border-blue-600'
										         : 'bg-white dark:bg-gray-900 text-gray-500 dark:text-gray-400 border-gray-300 dark:border-gray-600 line-through opacity-50'}"
									>
										{variant.name}
										<span class="font-mono tabular-nums {activeNames.has(variant.name) ? 'text-blue-200' : 'text-gray-400 dark:text-gray-500'}">
											{variant.score}%
										</span>
									</button>
								{/each}
							</div>
						</div>
					{/if}
				</div>

				{#if loadingCareer}
					<div class="grid grid-cols-1 xl:grid-cols-2 gap-6">
						<div class="space-y-3">
							{#each Array(5) as _}
								<div class="flex gap-4">
									<div class="w-3 h-3 rounded-full bg-gray-200 dark:bg-gray-700 mt-1.5 animate-pulse shrink-0"></div>
									<div class="flex-1 h-20 bg-gray-100 dark:bg-gray-800 rounded-lg animate-pulse"></div>
								</div>
							{/each}
						</div>
						<div class="h-64 bg-gray-100 dark:bg-gray-800 rounded-xl animate-pulse"></div>
					</div>
				{:else if career.length === 0}
					<div class="text-center py-12">
						<p class="text-sm text-gray-400 dark:text-gray-500 mb-3">No records match the current filters.</p>
						{#if isDirty}
							<button onclick={reset} class="text-sm text-blue-600 dark:text-blue-400 hover:underline">
								Reset filters
							</button>
						{/if}
					</div>
				{:else}
					<div class="grid grid-cols-1 xl:grid-cols-2 gap-6 items-start">

						<!-- ── Career Timeline ──────────────── -->
						<div>
							<h3 class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-3">
								Career Timeline
							</h3>
							<div class="relative">
								<div class="absolute left-[5px] top-2 bottom-2 w-px bg-gray-200 dark:bg-gray-700"></div>
								<ul class="space-y-3">
									{#each career as entry}
										<li class="pl-7 relative group">
											<div class="absolute left-0 top-3.5 w-[11px] h-[11px] rounded-full border-2 border-white dark:border-gray-950 ring-1
											            {isActive(entry) ? 'bg-blue-500 ring-blue-400' : 'bg-gray-300 dark:bg-gray-600 ring-gray-200 dark:ring-gray-700'}">
											</div>
											<div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl p-4 shadow-sm hover:shadow-md transition-shadow">
												<div class="flex items-start justify-between gap-2">
													<p class="text-sm font-semibold text-gray-900 dark:text-gray-100 leading-snug">{orgLabel(entry)}</p>
													<div class="flex items-center gap-1.5 shrink-0">
														{#if isActive(entry)}
															<span class="inline-flex items-center gap-1 text-xs font-medium text-green-700 dark:text-green-400 bg-green-50 dark:bg-green-950 border border-green-200 dark:border-green-800 rounded-full px-2 py-0.5">
																<span class="w-1.5 h-1.5 rounded-full bg-green-500"></span>
																Active
															</span>
														{/if}
														<!-- Remove button -->
														<button
															onclick={() => removeEntry(entry)}
															title="Remove this entry"
															class="opacity-0 group-hover:opacity-100 transition-opacity w-6 h-6 flex items-center justify-center
															       rounded-md text-gray-400 dark:text-gray-500 hover:text-red-500 dark:hover:text-red-400
															       hover:bg-red-50 dark:hover:bg-red-950"
														>
															<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
																<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/>
															</svg>
														</button>
													</div>
												</div>
												{#if entry.rank}
													<p class="text-sm text-gray-600 dark:text-gray-300 mt-0.5">{entry.rank}</p>
												{/if}
												{#if entry.person_name}
													<p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
														Identified as: <span class="font-medium">{entry.person_name}</span>
													</p>
												{/if}
												<div class="flex items-center gap-2 mt-2 flex-wrap">
													<span class="text-xs text-gray-400 dark:text-gray-500">
														{formatDate(entry.start_date)} → {formatDate(entry.end_date)}
													</span>
													{#if entry.tenure_days}
														<span class="text-xs font-medium text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-800 rounded-full px-2 py-0.5">
															{formatDuration(entry.tenure_days)}
														</span>
													{/if}
												</div>
											</div>
										</li>
									{/each}
								</ul>
							</div>
						</div>

						<!-- ── Individual Profile ───────────── -->
						<div class="space-y-4">
							<h3 class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-3">
								Individual Profile
							</h3>

							<div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl p-4 shadow-sm space-y-3">
								{#if employmentSpan().from}
									<div>
										<p class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-0.5">Employment span</p>
										<p class="text-sm text-gray-900 dark:text-gray-100">{employmentSpan().from} — {employmentSpan().to}</p>
									</div>
								{/if}
								<div>
									<p class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-0.5">Roles shown</p>
									<p class="text-sm text-gray-900 dark:text-gray-100">
										{career.length} role{career.length !== 1 ? 's' : ''}
										across {distinctOrgs.length} organisation{distinctOrgs.length !== 1 ? 's' : ''}
									</p>
								</div>
							</div>

							<div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl p-4 shadow-sm">
								<p class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-3">Organisations</p>
								<ul class="space-y-2">
									{#each distinctOrgs as org}
										<li class="flex items-start gap-2">
											<div class="w-1.5 h-1.5 rounded-full bg-gray-300 dark:bg-gray-600 shrink-0 mt-1.5"></div>
											<p class="text-sm text-gray-700 dark:text-gray-300 leading-snug">{org}</p>
										</li>
									{/each}
								</ul>
							</div>

							{#if isDirty}
								<button
									onclick={reset}
									class="w-full py-2 text-sm font-medium text-gray-600 dark:text-gray-400
									       border border-gray-200 dark:border-gray-700 rounded-xl
									       hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
								>
									Reset to full timeline
								</button>
							{/if}
						</div>

					</div>
				{/if}
			</div>
		{/if}
	</section>
</div>
