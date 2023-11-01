# ezBIDS

The secure, cloud-based service for the semi-automated mapping of entire sessions of neuroimaging data to the Brain Imaging Data Structure ([BIDS](https://bids.neuroimaging.io/)) standard.  

<img width="1450" alt="Screenshot 2023-11-01 at 11 50 48 AM" src="https://github.com/brainlife/ezbids/assets/2119795/2c054297-1503-4ebb-8718-336012c80b48">

### About

This is the development repository for a semi-supervised neuroimaging data files to [BIDS](https://bids.neuroimaging.io/) conversion web service. The web service is hosted securely at [brainlife.io/ezbods](https://brainlife.io/ezbids). Documentation and Tutorials will  

Unlike other BIDS converters, ezBIDS eliminates the need for code, and command line interfaces and automatically generates heuristic and configuration files (called ezBIDS Templates).

An inferential process analyzes the directory structure and sidecars of the data uploaded to provide an *educated guess* about the data types and content. A web-browser user interface presents the users with a *first guess* mapping of the uploaded data files into a BIDS structure. Finally, users provided with the opportunity to verify the *first guess* and modify the information provided as needed so as to best match the final BIDS structure. 

Data from all major scanner vendors can be directly uploaded to ezBIDS. ezBIDS provides options for the defacing of anatomical acquisitions.

The BIDS output can be downloaded back to the user's computer, or uploaded to open repositories such as
[brainlife.io](https://brainlife.io/), or in the future, [OpenNeuro](https://openneuro.org/).

### Usage
To access the ezBIDS web service, please visit https://brainlife.io/ezbids (Chrome or Firefox browser preferred).

A video demonstration of how to use ezBIDS can be found [here](https://www.youtube.com/watch?v=mY3_bmt_e80).

Users do not need to organize their uploaded data in any specific manner, so long as the data is non-anonymized. The uploaded data can contain any number of sub-folders, and users and may compress (e.g. zip, tar) their upload directory if users so choose. ezBIDS permits two types of data uploads:

1. **DICOM files** - Only DICOMs should be included in the upload. No specific organizational structure is required. 
2. **dcm2niix generated output (i.e. NIfTI, json, bval, and bvec) files** - Only these files (no DICOMs) should be included in the upload. We strongly recommend that the dcm2niix output not be anonymized (i.e. include *-ba n* in the dcm2niix command), in which case, no specific organizational structure is required.

Should users feel the need to anonymize their data before uploading, we strongly recommend that subjects (and sessions) be organized into subject (and session) folders, with explicit labeling of the subject (and session) IDs (e.g. */MRI_data/sub-01/ses-01/DICOMS*). Failure to do so for non-anonymized data will result in additional work.

### Backend Workflow
*(optional reading, if interested in the backend API workflow)*

1. Uploading Data

When a user starts uploading data, ezBIDS will create a new *session* using `(post)/session` API. A session organize each ezBIDS upload/conversion process. For each session, a new DB/session collection is created with the mongo ID as session ID, and create a unique working directory using the sessionID on the backend server where all uploaded data is stored. When all files are successfully uploaded, client makes `(patch)/session/uploaded/:session_id` API call and set the session state to "uploaded" to let the ezBIDS handler knows that the session is ready to being preprocessing.

2. Preprocessing Data

The backend server polls for uploaded sessions, and when it finds "uploaded" session, it will launch the preprocessing script. It sets the session state to "preprocessing". It basically unzip all zipped files, run dcm2niix and create a `list` file containing all the nifti and sidecar json. analyzer.py uses this to analyze each nifti files and at the end create `ezBIDS_core.json`. When the preprocessing completes, the session state will be set to "analyzed". The preprocessing step then load ezBIDS_core.json json and copy the content to DB/ezBIDS collection (not session collection) under `original` key.

3. User interact with the session via web UI.

Web UI detects the preprocessing completed by polling for session state, and load the content of ezBIDS_core.json via `(get)/download/:session_id/ezBIDS_core.json` API. User then view / correct the content of ezBIDS_core.json. 

4. (optionally) User request for defacing

Before user finalizes editing the information, they are given chance to deface anatomical images. When user requests defacing, the UI will make `(post)/session/:sessino_id/deface` API call with a list of images to deface.
The backend stores this information as `deface.json` in the workdir and set the session state to "deface". The backend defacing handler looks "deface" state session and set it to "defacing" and launch `deface.sh` script. Once defacing is completed, it will set the session state to "defaced".

`deface.sh` create the following files under the workdir.

* deface.finished (list the anatomy files defaced successfully) 
* deface.failed (list the anatomy files that failed defacing)

UI polls these files to determine which files are successfully defaced (or not). When defacing is completed, the status will be set to "defaced". User can then choose if they want to use the defaced version of anatomy file or not (each object will have a field named `defaceSelection` set to either "original" or "defaced" to indicate which image to use). 

5. Finalize

When user clicks "finalize" button, UI makes an API call for `(post)/session/:session_id/finalize` API. The UI passes the following content from the memory ($root).

```
{
    datasetDescription: this.datasetDescription,
    readme: this.readme,
    participantsColumn: this.participantsColumn,
    subjects: this.subjects, //for phenotype
    objects: this.objects,
    entityMappings,
}
```

The API then store this information as `finalized.json` in workdir, and copy the content to DB/ezBIDS collection under `updated` key (to contrast with `original` key). The session status will be set to "finalized". This kicks off finalized handler on the server side and the handler reset the status to "bidsing" and run `bids.sh` script to generate the bids structure according to the information stored at the object level. Once it finishes, the session status will be set to "finished".

6. User Get BIDS

Once session status becomes "finished", user will be then allowed to download the final "bids" directory via the download API, or send to other cloud resources

### Authors
- [Soichi Hayashi](soichih@gmail.com)
- [Daniel Levitas](dlevitas@iu.edu)
- [Franco Pestilli](pestilli@utexas.edu)

### Funding Acknowledgement
brainlife.io is publicly funded and for the sustainability of the project it is helpful to Acknowledge the use of the platform. We kindly ask that you acknowledge the funding below in your code and publications. Copy and past the following lines into your repository when using this code.

[![NSF-BCS-1734853](https://img.shields.io/badge/NSF_BCS-1734853-blue.svg)](https://nsf.gov/awardsearch/showAward?AWD_ID=1734853)
[![NSF-BCS-1636893](https://img.shields.io/badge/NSF_BCS-1636893-blue.svg)](https://nsf.gov/awardsearch/showAward?AWD_ID=1636893)
[![NSF-ACI-1916518](https://img.shields.io/badge/NSF_ACI-1916518-blue.svg)](https://nsf.gov/awardsearch/showAward?AWD_ID=1916518)
[![NSF-IIS-1912270](https://img.shields.io/badge/NSF_IIS-1912270-blue.svg)](https://nsf.gov/awardsearch/showAward?AWD_ID=1912270)
[![NIH-NIBIB-R01EB029272](https://img.shields.io/badge/NIH_NIBIB-R01EB029272-green.svg)](https://grantome.com/grant/NIH/R01-EB029272-01)
[![NIH-NIMH-R01MH126699]](https://img.shields.io/badge/NIH_NIMH-R01MH126699-green.svg)](https://grantome.com/grant/NIH/R01-EB029272)

### Citations
We ask that you the following articles when publishing papers that used data, code or other resources created by the brainlife.io community.

1. Levias, D. et al. **In review**

### This repo was bootstrapped by

```
npm init vite@latest ui2 -- --template vue-ts
```

### Development Environment

A local development instance of ezBIDS can be launched by first git cloning this repo, then running `./dev.sh` on a docker enabled machine. When everything is built/running, you should be able to reach the dev instance at http://localhost:3000/



Copyright © 2022 brainlife.io at University of Texas at Austin

