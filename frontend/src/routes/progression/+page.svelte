<script lang="ts">
	import { people } from '$lib/api';
	import type { PersonResult, EmploymentEntry, NameVariant } from '$lib/api';
	import { isAuthenticated, authReady } from '$lib/auth';
	import { goto } from '$app/navigation';
	import ConfidenceSlider from '$lib/components/ConfidenceSlider.svelte';
	import NameVariantZones from '$lib/components/NameVariantZones.svelte';
	import PersonSearch from '$lib/components/PersonSearch.svelte';

	$effect(() => {
		if ($authReady && !$isAuthenticated) goto('/login?redirect=/progression');
	});

	// ---------------------------------------------------------------------------
	// State
	// ---------------------------------------------------------------------------
	let selected        = $state<PersonResult | null>(null);
	let originalCareer  = $state<EmploymentEntry[]>([]);
	let career          = $state<EmploymentEntry[]>([]);
	let nameVariants    = $state<NameVariant[]>([]);
	let activeNames     = $state<Set<string>>(new Set());

	let loadingCareer   = $state(false);
	let careerError     = $state('');

	let confidenceThreshold = $state(95);

	// ---------------------------------------------------------------------------
	// Select person
	// ---------------------------------------------------------------------------
	async function selectPerson(person: PersonResult) {
		selected = person; career = []; originalCareer = []; nameVariants = []; activeNames = new Set();
		careerError = ''; loadingCareer = true;
		try { await loadCareerFor(person.name); }
		finally { loadingCareer = false; }
	}

	const BROAD_THRESHOLD = 0.5;

	async function loadCareerFor(name: string) {
		const [variants, raw] = await Promise.all([
			people.similarNames(name, 15, BROAD_THRESHOLD),
			people.careerByName(name, true, BROAD_THRESHOLD)
		]);
		nameVariants = variants;
		const sorted = [...raw].sort((a, b) => {
			if (!a.start_date) return 1;
			if (!b.start_date) return -1;
			return a.start_date.localeCompare(b.start_date);
		});
		originalCareer = sorted;
		const highConf = new Set(variants.filter(v => v.score >= confidenceThreshold).map(v => v.name));
		activeNames = highConf;
		career = sorted.filter(e => !e.person_name || highConf.has(e.person_name));
	}

	function clearSelection() {
		selected = null; career = []; originalCareer = []; nameVariants = []; activeNames = new Set();
	}

	// ---------------------------------------------------------------------------
	// Derived helpers
	// ---------------------------------------------------------------------------
	const variantScoreMap = $derived(new Map(nameVariants.map(v => [v.name, v.score])));

	const defaultActiveNames = $derived(
		new Set(nameVariants.filter(v => v.score >= confidenceThreshold).map(v => v.name))
	);

	const expectedCareerLength = $derived(
		originalCareer.filter(e => !e.person_name || activeNames.has(e.person_name)).length
	);

	const isDirty = $derived(
		activeNames.size !== defaultActiveNames.size ||
		[...activeNames].some(n => !defaultActiveNames.has(n)) ||
		career.length < expectedCareerLength
	);

	function isLowConfidence(entry: EmploymentEntry): boolean {
		if (!entry.person_name) return false;
		const score = variantScoreMap.get(entry.person_name);
		return score !== undefined && score < confidenceThreshold;
	}

	// ---------------------------------------------------------------------------
	// Toggle variant
	// ---------------------------------------------------------------------------
	function toggleName(name: string) {
		const next = new Set(activeNames);
		if (next.has(name)) { next.delete(name); } else { next.add(name); }
		activeNames = next;
		const removedIds = new Set(
			originalCareer.filter(e => !career.some(c => c.id === e.id)).map(e => e.id)
		);
		career = originalCareer.filter(
			e => !removedIds.has(e.id) && (!e.person_name || next.has(e.person_name))
		);
	}

	function removeEntry(entry: EmploymentEntry) {
		career = career.filter(e => e !== entry);
	}

	function reset() {
		activeNames = new Set(defaultActiveNames);
		career = originalCareer.filter(e => !e.person_name || defaultActiveNames.has(e.person_name));
	}

	// ---------------------------------------------------------------------------
	// Profile stats
	// ---------------------------------------------------------------------------
	const employmentSpan = $derived(() => {
		const starts = career.map(e => e.start_date).filter(Boolean) as string[];
		const ends   = career.map(e => e.end_date).filter(Boolean) as string[];
		return {
			from: starts.length ? formatDate(starts[0]) : null,
			to: career.some(e => !e.end_date) ? 'Present' : (ends.length ? formatDate(ends[ends.length - 1]) : null)
		};
	});

	const distinctOrgs = $derived([...new Set(career.map(e => orgLabel(e)))]);

	// ---------------------------------------------------------------------------
	// Helpers
	// ---------------------------------------------------------------------------
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

	function orgLabel(e: EmploymentEntry) { return e.org_name ?? e.entity_name ?? 'Unknown organisation'; }
	function isActive(e: EmploymentEntry) { return !e.end_date; }
	function isSamePerson(e: EmploymentEntry) { return !selected || e.person_id == null || e.person_id === selected.id; }
</script>

<div class="flex-1 flex flex-col lg:flex-row overflow-hidden" style="height: calc(100vh - 3.5rem - 49px)">
	<!-- ── Left panel ─────────────────────────────────── -->
	<aside class="w-full lg:w-80 xl:w-96 shrink-0 flex flex-col border-b lg:border-b-0 lg:border-r border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900">
		<div class="p-4 border-b border-gray-100 dark:border-gray-800 space-y-3">
			<h1 class="text-sm font-semibold text-gray-900 dark:text-gray-100">Career Progression</h1>

			<PersonSearch
				placeholder="Search by name…"
				{confidenceThreshold}
				{selected}
				onselect={selectPerson}
				onclear={clearSelection}
			/>

			<ConfidenceSlider bind:value={confidenceThreshold} />
		</div>

		<!-- Name variants (shown below search when selected) -->
		{#if selected && !loadingCareer && nameVariants.length > 0}
			<div class="p-4 border-b border-gray-100 dark:border-gray-800 space-y-2">
				<div class="flex items-center justify-between">
					<p class="text-xs font-medium text-gray-500 dark:text-gray-400">
						Name variants — drag between zones to adjust timeline
					</p>
					{#if isDirty}
						<button onclick={reset} class="text-xs text-blue-600 dark:text-blue-400 hover:underline">
							Reset
						</button>
					{/if}
				</div>
				<NameVariantZones
					{nameVariants}
					{activeNames}
					{confidenceThreshold}
					ontoggle={toggleName}
				/>
			</div>
		{/if}
	</aside>

	<!-- ── Right panel ────────────────────────────────── -->
	<section class="flex-1 overflow-y-auto bg-gray-50 dark:bg-gray-950">
		{#if !selected}
			<div class="h-full flex items-center justify-center p-8">
				<div class="text-center">
					<svg class="w-12 h-12 text-gray-200 dark:text-gray-700 mx-auto mb-3" fill="none" stroke="currentColor" stroke-width="1" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z"/>
					</svg>
					<p class="text-sm text-gray-400">Select a person to view their career history</p>
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
							{#if selected.email}<p class="text-sm text-gray-500 truncate">{selected.email}</p>{/if}
							{#if selected.tel}<p class="text-xs text-gray-400">{selected.tel}</p>{/if}
						</div>
						{#if !loadingCareer && career.length > 0}
							<div class="shrink-0 text-right">
								<p class="text-lg font-bold text-gray-900 dark:text-gray-100">{career.length}</p>
								<p class="text-xs text-gray-400">{career.length !== originalCareer.length ? `of ${originalCareer.length} ` : ''}roles</p>
							</div>
						{/if}
					</div>
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
				{:else if careerError}
					<div class="text-center py-12">
						<p class="text-sm text-red-500">{careerError}</p>
					</div>
				{:else if career.length === 0}
					<div class="text-center py-12">
						<p class="text-sm text-gray-400 mb-3">No records match the current filters.</p>
						{#if isDirty}
							<button onclick={reset} class="text-sm text-blue-600 hover:underline">Reset filters</button>
						{/if}
					</div>
				{:else}
					<div class="grid grid-cols-1 xl:grid-cols-2 gap-6 items-start">

						<!-- ── Career Timeline ──────────── -->
						<div>
							<h3 class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-3">
								Career Timeline
							</h3>
							<div class="relative">
								<div class="absolute left-[5px] top-2 bottom-2 w-px bg-gray-200 dark:bg-gray-700"></div>
								<ul class="space-y-3">
									{#each career as entry}
										<li class="pl-7 relative group {!isSamePerson(entry) ? 'opacity-60' : ''}">
											<div class="absolute left-0 top-3.5 w-[11px] h-[11px] rounded-full border-2 border-white dark:border-gray-950 ring-1
											            {isSamePerson(entry)
											              ? (isActive(entry) ? 'bg-blue-500 ring-blue-400' : 'bg-gray-300 dark:bg-gray-600 ring-gray-200 dark:ring-gray-700')
											              : 'bg-amber-400 ring-amber-300'}">
											</div>
											<div class="rounded-xl p-4 shadow-sm hover:shadow-md transition-shadow
											            {isSamePerson(entry)
											              ? 'bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700'
											              : 'bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800/50'}">
												<div class="flex items-start justify-between gap-2">
													<div class="min-w-0">
														<p class="text-sm font-semibold text-gray-900 dark:text-gray-100 leading-snug">{orgLabel(entry)}</p>
														{#if entry.person_name && entry.person_name !== selected?.name}
															<p class="text-xs text-gray-400 mt-0.5 italic">as {entry.person_name}</p>
														{/if}
													</div>
													<div class="flex items-center gap-1.5 shrink-0 flex-wrap justify-end">
														{#if !isSamePerson(entry)}
															<span class="inline-flex items-center text-xs font-medium text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-950 border border-amber-200 dark:border-amber-800 rounded-full px-2 py-0.5">
																Different person?
															</span>
														{/if}
														{#if isLowConfidence(entry)}
															<span class="inline-flex items-center text-xs font-medium text-purple-700 dark:text-purple-400 bg-purple-50 dark:bg-purple-950 border border-purple-200 dark:border-purple-800 rounded-full px-2 py-0.5">
																Low confidence
															</span>
														{/if}
														{#if isActive(entry)}
															<span class="inline-flex items-center gap-1 text-xs font-medium text-green-700 dark:text-green-400 bg-green-50 dark:bg-green-950 border border-green-200 dark:border-green-800 rounded-full px-2 py-0.5">
																<span class="w-1.5 h-1.5 rounded-full bg-green-500"></span>Active
															</span>
														{/if}
														<button onclick={() => removeEntry(entry)} title="Remove this entry"
															class="opacity-0 group-hover:opacity-100 transition-opacity w-6 h-6 flex items-center justify-center
															       rounded-md text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950">
															<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
																<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/>
															</svg>
														</button>
													</div>
												</div>
												{#if entry.rank}
													<p class="text-sm text-gray-600 dark:text-gray-300 mt-0.5">{entry.rank}</p>
												{/if}
												<div class="flex items-center gap-2 mt-2 flex-wrap">
													<span class="text-xs text-gray-400">
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

						<!-- ── Individual Profile ─────────── -->
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
										{career.length} role{career.length !== 1 ? 's' : ''} across {distinctOrgs.length} organisation{distinctOrgs.length !== 1 ? 's' : ''}
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
								<button onclick={reset}
									class="w-full py-2 text-sm font-medium text-gray-600 dark:text-gray-400
									       border border-gray-200 dark:border-gray-700 rounded-xl
									       hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors">
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
