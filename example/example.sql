USE EXAMPLE;

DROP TABLE IF EXISTS `SENSOR_EVENT`;
CREATE TABLE `SENSOR_EVENT` (
  `ID` int(11) NOT NULL AUTO_INCREMENT,
  `RAW_VALUE` FLOAT(7,4) DEFAULT 0,
  `EVENT_TIMESTAMP` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`ID`),
  UNIQUE KEY `ID_UNIQUE` (`ID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;