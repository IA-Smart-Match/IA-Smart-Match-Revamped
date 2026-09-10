/**
 * One list, shown a page at a time (TRACK T1 §B).
 *
 * Nothing in this application paginates. Every list renders every row the last
 * read returned, so a Connector with a full roster scrolls past a hundred
 * contacts to reach the submit button underneath them, and a student with a
 * term of published events scrolls past the term to reach the agenda. This
 * component is the single answer to that, applied everywhere rather than
 * reinvented per page.
 *
 * ## What it is, stated as a boundary
 *
 * **It is a view over an array that has already been fetched.** It takes
 * `items`, slices `items`, and hands the slice back. It issues no request, owns
 * no query, holds no cursor, and has no opinion about where the array came
 * from. Server-side paging is a different feature with a different contract —
 * an offset, a limit, and a server-counted total — and a component that did
 * both would make it impossible to tell, from a page's source, which one that
 * page had. `tests/unit/test_frontend_paged_list_contract.py` pins the
 * separation at the source level.
 *
 * **It counts only the array it was handed.** The range line says "of N
 * loaded", not "of N", because N is the length of what this browser currently
 * holds and is not a population figure. Several pages read routes that stop
 * sending at a server-side cap and say so with their own `truncated` notice;
 * that notice means "the server stopped sending" and this component's range
 * line means "this page is not showing you everything it has". They are
 * different statements about different quantities and both must survive
 * (ADR-0011 rule 1 in its list-shaped form: an unknown population is not
 * reported as the number of rows that happened to arrive).
 *
 * ## Selection is the caller's, and that is what makes it survive
 *
 * A selected row is a *fact about an entity*, not a property of a rendered
 * row: `selectedRequestId` and `selectedSubjectIds` on `CoordinatorMatchRuns`
 * are ids, held in that page's own state. This component never touches them,
 * which is precisely why turning a page cannot clear them — there is no code
 * path here that could. Checked candidates on page 1 are still checked and
 * still submitted after a Connector pages to page 3 and back, and the
 * submitted count keeps counting all of them, because paging changes what is
 * *drawn* and nothing else.
 *
 * That is also why the render prop hands back the slice rather than this
 * component rendering rows itself: the caller keeps its own list element, its
 * own row component, and its own selection wiring, and gains paging without
 * restructuring any of it.
 *
 * ## Controls above *and* below
 *
 * Both bars are rendered, and that is the point of the exercise rather than a
 * flourish. Paging controls only at the top of a fifty-row list leave the
 * reader at the bottom of the list with nowhere to go but back up, which is the
 * same scroll the pagination was meant to remove. The two bars drive one piece
 * of state, so they can never disagree; their ids and accessible names differ
 * because two controls in one document may not share an id.
 *
 * Every control is a real `<button>` or a real labelled `<select>`, reachable
 * and operable from the keyboard. The Radix pagination primitive in
 * `ui/pagination.tsx` renders its links as bare `<a>` elements with no `href`,
 * which are not focusable and cannot be activated by keyboard; so the nav
 * landmark, list structure and ellipsis come from that primitive — no new
 * dependency — while the interactive elements are buttons wearing the same
 * `buttonVariants` styling the primitive's links wear.
 */

import { useMemo, useState, type ReactNode } from "react";

import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
} from "./ui/pagination";
import { buttonVariants } from "./ui/button";
import { cn } from "./ui/utils";

/**
 * The page sizes offered, smallest first.
 *
 * Four fixed choices rather than a free-text field: these are the rungs a
 * reader picks between, and an arbitrary number would only invite a page size
 * of one. Below the smallest rung no choice here can change anything, which is
 * what `MINIMUM_PAGEABLE_LENGTH` uses.
 */
const PAGE_SIZE_OPTIONS = [5, 10, 25, 50] as const;

type PageSizeOption = (typeof PAGE_SIZE_OPTIONS)[number];

/** The size a list gets when its caller expresses no preference. */
const DEFAULT_PAGE_SIZE: PageSizeOption = 10;

/**
 * Below this many rows the controls are not drawn at all.
 *
 * A list shorter than the smallest offered page size fits on one page at every
 * available setting, so a control bar there would be two rows of chrome that
 * can do nothing.
 */
const MINIMUM_PAGEABLE_LENGTH = PAGE_SIZE_OPTIONS[0];

/**
 * How many numbered pages are drawn before the window collapses to
 * first / neighbours / last around an ellipsis.
 */
const MAX_NUMBERED_PAGES = 7;

export interface PagedListProps<TItem> {
  /**
   * The rows to page over — already fetched, in the order they should appear.
   *
   * This component reads its length and slices it. It does not sort, filter,
   * de-duplicate or re-order, because each of those is a decision the page
   * above has already made for its own stated reasons.
   */
  items: readonly TItem[];
  /**
   * What these rows are, in the plural and in the reader's words — "Speaker
   * Requests", "published events", "redeemed tickets".
   *
   * It appears in the range line and in the accessible names of the controls,
   * so that a screen reader on a page carrying two lists is told which one a
   * given "Next page" belongs to.
   */
  label: string;
  /**
   * A prefix unique within the rendered document, used to build the ids that
   * tie each page-size `<select>` to its `<label>`.
   *
   * Pages that render two lists must pass two different prefixes; nothing can
   * check that from here, but a duplicated id is visible in any accessibility
   * audit of the page.
   */
  idPrefix: string;
  /** The page size to start at. Defaults to ten. */
  initialPageSize?: PageSizeOption;
  /**
   * Renders the visible slice.
   *
   * The caller supplies its own list element and row components; this receives
   * only the rows that belong on the current page, in their original order.
   */
  children: (visibleItems: readonly TItem[]) => ReactNode;
}

/**
 * The page numbers to draw, with `null` standing for an elided run.
 *
 * Every page stays reachable when the window collapses: first and last are
 * always drawn, the current page always has its neighbours, and anything not
 * drawn is at most a couple of steps away through them.
 */
function buildPageWindow(currentPage: number, pageCount: number): readonly (number | null)[] {
  if (pageCount <= MAX_NUMBERED_PAGES) {
    return Array.from({ length: pageCount }, (_, index) => index + 1);
  }

  const neighbours = [currentPage - 1, currentPage, currentPage + 1].filter(
    (page) => page > 1 && page < pageCount,
  );
  const window: (number | null)[] = [1];

  if (neighbours.length > 0 && neighbours[0] > 2) {
    window.push(null);
  }
  window.push(...neighbours);
  if (neighbours.length > 0 && neighbours[neighbours.length - 1] < pageCount - 1) {
    window.push(null);
  }
  window.push(pageCount);

  return window;
}

/** The shared styling of a control-bar button, current page or not. */
function controlClassName(isCurrent: boolean): string {
  return cn(
    buttonVariants({ variant: isCurrent ? "outline" : "ghost", size: "default" }),
    "h-9 px-3 text-sm",
  );
}

interface PagingControlsProps {
  /** `"top"` or `"bottom"` — distinguishes the two bars' ids and names. */
  position: string;
  label: string;
  idPrefix: string;
  currentPage: number;
  pageCount: number;
  pageSize: PageSizeOption;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: PageSizeOption) => void;
}

/**
 * One control bar: how many rows per page, and which page. Rendered twice per
 * list, above it and below it, both bound to the same state.
 */
function PagingControls({
  position,
  label,
  idPrefix,
  currentPage,
  pageCount,
  pageSize,
  onPageChange,
  onPageSizeChange,
}: PagingControlsProps) {
  const selectId = `${idPrefix}-page-size-${position}`;

  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-2">
        <label htmlFor={selectId} className="text-sm text-muted-foreground">
          {label} per page
        </label>
        <select
          id={selectId}
          value={pageSize}
          onChange={(event) => onPageSizeChange(Number(event.target.value) as PageSizeOption)}
          className="rounded-lg border border-border/70 bg-background px-2 py-1 text-sm"
        >
          {PAGE_SIZE_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </div>

      <Pagination
        aria-label={`${label} pages (${position} of the list)`}
        className="mx-0 w-auto justify-end"
      >
        <PaginationContent>
          <PaginationItem>
            <button
              type="button"
              onClick={() => onPageChange(currentPage - 1)}
              disabled={currentPage <= 1}
              aria-label={`Previous page of ${label}`}
              className={cn(controlClassName(false), "disabled:opacity-50")}
            >
              Previous
            </button>
          </PaginationItem>

          {buildPageWindow(currentPage, pageCount).map((page, index) => (
            <PaginationItem key={page === null ? `gap-${index}` : page}>
              {page === null ? (
                <PaginationEllipsis />
              ) : (
                <button
                  type="button"
                  onClick={() => onPageChange(page)}
                  aria-label={`Page ${page} of ${label}`}
                  aria-current={page === currentPage ? "page" : undefined}
                  className={controlClassName(page === currentPage)}
                >
                  {page}
                </button>
              )}
            </PaginationItem>
          ))}

          <PaginationItem>
            <button
              type="button"
              onClick={() => onPageChange(currentPage + 1)}
              disabled={currentPage >= pageCount}
              aria-label={`Next page of ${label}`}
              className={cn(controlClassName(false), "disabled:opacity-50")}
            >
              Next
            </button>
          </PaginationItem>
        </PaginationContent>
      </Pagination>
    </div>
  );
}

/**
 * Pages an already-fetched array and renders the current slice through
 * `children`.
 *
 * ```tsx
 * <PagedList items={requests} label="Speaker Requests" idPrefix="match-run-requests">
 *   {(visible) => (
 *     <ul className="space-y-3">
 *       {visible.map((request) => (
 *         <RequestRow key={request.request_id} request={request} … />
 *       ))}
 *     </ul>
 *   )}
 * </PagedList>
 * ```
 */
export function PagedList<TItem>({
  items,
  label,
  idPrefix,
  initialPageSize = DEFAULT_PAGE_SIZE,
  children,
}: PagedListProps<TItem>) {
  const [pageSize, setPageSize] = useState<PageSizeOption>(initialPageSize);
  const [requestedPage, setRequestedPage] = useState(1);

  // The page is clamped on the way out rather than corrected by an effect. The
  // array can shrink underneath this component — a refetch, a filter above it —
  // and an effect would render one frame of an empty page before fixing it,
  // which reads as "there is nothing here".
  const pageCount = Math.max(1, Math.ceil(items.length / pageSize));
  const currentPage = Math.min(Math.max(requestedPage, 1), pageCount);

  const firstIndex = (currentPage - 1) * pageSize;
  const visibleItems = useMemo(
    () => items.slice(firstIndex, firstIndex + pageSize),
    [items, firstIndex, pageSize],
  );

  function changePageSize(nextPageSize: PageSizeOption) {
    setPageSize(nextPageSize);
    // The reader's place in the list is not recoverable across a size change —
    // page 4 of twenty-five-per-page is not page 4 of five-per-page — so the
    // honest move is to return to the start rather than land somewhere
    // arbitrary that looks deliberate.
    setRequestedPage(1);
  }

  // A list no page size could split is handed back whole, with no chrome.
  if (items.length < MINIMUM_PAGEABLE_LENGTH) {
    return <>{children(items)}</>;
  }

  const controls = (position: string) => (
    <PagingControls
      position={position}
      label={label}
      idPrefix={idPrefix}
      currentPage={currentPage}
      pageCount={pageCount}
      pageSize={pageSize}
      onPageChange={setRequestedPage}
      onPageSizeChange={changePageSize}
    />
  );

  return (
    <div className="space-y-3">
      {controls("top")}

      {/*
        "of N loaded" and not "of N": N is how many rows this browser is
        currently holding, which is a different quantity from how many exist.
        Where a page also renders a server `truncated` notice, that notice is
        the one that speaks about the second quantity, and it stays.
      */}
      <p className="text-xs text-muted-foreground" aria-live="polite">
        Showing {firstIndex + 1}&ndash;{firstIndex + visibleItems.length} of {items.length} loaded{" "}
        {label.toLowerCase()}.
      </p>

      {children(visibleItems)}

      {controls("bottom")}
    </div>
  );
}
