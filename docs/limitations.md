# Limitations

## Scientific

* **Labels are model outputs.** The U-Net learns WorldCover's classification, including its errors (about 23–26% overall disagreement with independent reference data, per ESA). Agreement with these labels is not accuracy.
* **Definition of forest.** "Tree cover" includes plantations, orchards, agroforestry and regrowth, and differs from legal or FAO definitions. Plantation harvest appears as potential loss.
* **Degradation is mostly invisible.** Selective logging and understorey fire under an intact canopy are rarely detectable at 10–20 m.
* **Effective resolution.** Half of the input bands are natively 20 m. With the 0.5 ha minimum mapping unit, smaller clearings are excluded.
* **Cause and legality.** Imagery cannot establish why tree cover was lost, who removed it or whether it was legal. Fire-like spectral change is an annotation, not an attribution.
* **Area estimates are mapped areas**, with boundary uncertainty only. They are biased by omission and commission errors that are not quantified without a reference sample.
* **Domain.** Trained on tropical moist and dry forest regions in South America plus one Indonesian region, in the dry season. Performance elsewhere (temperate or boreal forest, African forests, wet-season imagery, snow) is unknown and likely poorer.
* **Bare/sparse class.** It is rare in the training regions (< 1% of labelled pixels), so its predictions are unreliable.
* **Phenology.** Deciduous dry forest loses leaves in the dry season and can look non-forest. Same-season comparisons reduce, but do not remove, this risk.

## Data access

* Earth Search Collection 1 has temporal gaps (for example 2022 over parts of the Amazon); the legacy collection fills them with harmonised radiometry.
* Persistent cloud in the humid tropics can leave a period with no valid observation. Sylva reports this as invalid rather than filling it in.
* Dynamic World needs an Earth Engine account; it is supported but was not used for the delivered model.
* CDSE authenticated downloads need user credentials and were not verified end to end during development.
* Hansen GFC v1.13 ends in 2025: changes after 2025 cannot be corroborated.
* Providers can change APIs or URLs; the provider layer isolates this, and ingested data is cached locally.

## Computational

* CPU training of the standard model takes hours. The quick profile trades accuracy for time.
* The AOI size is capped (2,500 km² by default) to keep memory and download size manageable.

## Deployment

* Development and automated testing ran on Linux. The Windows scripts are written for Windows PowerShell 5.1 and 7, but they were not executed on a Windows machine during development (see the README for the Windows verification workflow).
* The application is designed for local, single-user use: there is no authentication on the API.
