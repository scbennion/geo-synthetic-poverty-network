"""Assemble a synthesis run's population, workplaces, verification, and errors."""
import geopandas as gpd
import pandas as pd
from loguru import logger


def collect_results(results, X):
    # Check if the operation is for Population data
    if X == "Pop":
        logger.info("--Collecting Population")
        temp_df = pd.DataFrame()
        # Concatenate all DataFrame results into a single DataFrame
        for i in results:
            temp_df = pd.concat([temp_df, i])

        # Reset index for the combined DataFrame and drop the 'code' column
        temp_df = temp_df.reset_index().drop(['code'], axis=1)
        # Rename the first column to 'id'
        temp_df.rename(columns={temp_df.columns[0]: 'id'}, inplace=True)
        # Convert the DataFrame to a GeoDataFrame, specifying the 'geometry' column
        pop_gdf = gpd.GeoDataFrame(temp_df, geometry='geometry')
        # Set the CRS to EPSG:4269
        pop_gdf = pop_gdf.set_crs('EPSG:4269', allow_override=True)

        # Extract longitude and latitude from the 'geometry' column
        pop_gdf['long'] = pop_gdf['geometry'].x
        pop_gdf['lat'] = pop_gdf['geometry'].y
        # Return the GeoDataFrame with Population data
        return pop_gdf

    # Check if the operation is for Work data
    elif X == "Work":
        logger.info("--Collecting Workplaces")
        wp = pd.DataFrame()
        # Concatenate all DataFrame results into a single DataFrame
        for j in results:
            wp = pd.concat([wp, j])
        # Reset index for the combined DataFrame
        wp = wp.reset_index()
        # Rename the first two columns to 'wp' and 'geometry'
        wp.rename(columns={wp.columns[0]: 'wp', wp.columns[1]: 'geometry'}, inplace=True)

        wp_gdf = gpd.GeoDataFrame(wp, geometry='geometry')
        # Set the CRS to EPSG:4269
        wp_gdf = wp_gdf.set_crs('EPSG:4269', allow_override=True)
        #wp_gdf.set_crs('EPSG:4269', inplace=True)
        # Extract longitude and latitude from the 'geometry' column
        wp_gdf['long'] = wp_gdf['geometry'].x
        wp_gdf['lat'] = wp_gdf['geometry'].y
        # Return the DataFrame with Work data
        return wp_gdf

    # Handle other types of data for verification
    elif X == "Verification":
        logger.info("--Collecting Verification")
        ver_df = pd.DataFrame()
        # Concatenate and transpose each result, then combine into a single DataFrame
        for i in results:
            ver_df = pd.concat([ver_df, i.transpose()], axis=1)
        # Return the transposed and combined DataFrame
        return ver_df.T

    else:
        logger.info("--Collecting Tract with error")
        if len(results) != 0:
            err_df = pd.DataFrame()
            for _ in results:
                err_df = pd.concat([err_df, pd.DataFrame(_).transpose()])
            err_df = err_df.reset_index(drop=True)
            err_df.rename(columns={err_df.columns[0]: 'tract', err_df.columns[1]: 'error_message'}, inplace=True)
            return err_df
        else:
            logger.info("--No Error Tract")
