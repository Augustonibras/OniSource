type CountryResult = {
  country?: unknown;
};

function normalizeLocation(value: string) {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[_-]+/g, " ")
    .trim()
    .toLowerCase();
}

export function isSouthAmericaLocation(
  locationType: string,
  locationValue: string,
) {
  if (locationType !== "continent") {
    return false;
  }
  const normalized = normalizeLocation(locationValue);
  return normalized === "south america" || normalized === "america do sul";
}

export function isBrazil(country: unknown) {
  if (typeof country !== "string") {
    return false;
  }
  const normalized = normalizeLocation(country);
  return /(^|\s)(brazil|brasil)(\s|$)/.test(normalized);
}

export function filterSalesResultsByLocation<T extends CountryResult>(
  results: T[],
  locationType: string,
  locationValue: string,
) {
  if (!isSouthAmericaLocation(locationType, locationValue)) {
    return results;
  }
  return results.filter((result) => !isBrazil(result.country));
}
